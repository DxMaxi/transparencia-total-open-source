import hashlib
import os
import stat
import uuid
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path, PurePosixPath
from typing import Protocol

from app.core.config import Settings
from app.models.archive import (
    PrivateRawDocument,
    RawArchiveReceipt,
    RawArchiveVerification,
)


class RawArchiveConfigurationError(RuntimeError):
    """O arquivo privado não está configurado de forma segura."""


class RawArchiveIntegrityError(RuntimeError):
    """Um objeto existente não corresponde à sua chave content-addressed."""


class RawDocumentArchive(Protocol):
    def archive(self, document: PrivateRawDocument) -> RawArchiveReceipt: ...

    def verify(
        self,
        *,
        storage_key: str,
        expected_sha256: str,
        expected_byte_size: int,
    ) -> RawArchiveVerification: ...


def _chunks(handle: object, size: int = 1024 * 1024) -> Iterator[bytes]:
    while True:
        chunk = handle.read(size)  # type: ignore[attr-defined]
        if not chunk:
            return
        yield chunk


class ContentAddressedFileArchive:
    """Arquivo local privado, imutável e endereçado por SHA-256.

    Não disponibiliza operações de leitura de conteúdo, substituição ou
    eliminação. ``verify`` só calcula tamanho e hash para inspeção de integridade.
    """

    storage_backend = "FILESYSTEM"

    def __init__(self, root: Path, *, repository_root: Path | None = None) -> None:
        if not root.is_absolute():
            raise RawArchiveConfigurationError("RAW_ARCHIVE_ROOT deve ser um caminho absoluto")
        if root.is_symlink():
            raise RawArchiveConfigurationError(
                "RAW_ARCHIVE_ROOT não pode ser uma ligação simbólica"
            )

        resolved_root = root.resolve(strict=False)
        project_root = (repository_root or Path(__file__).resolve().parents[3]).resolve()
        if resolved_root == project_root or resolved_root.is_relative_to(project_root):
            raise RawArchiveConfigurationError("RAW_ARCHIVE_ROOT deve ficar fora do repositório")
        if resolved_root.exists() and not resolved_root.is_dir():
            raise RawArchiveConfigurationError("RAW_ARCHIVE_ROOT tem de identificar um diretório")
        self.root = resolved_root

    @classmethod
    def from_settings(cls, settings: Settings) -> "ContentAddressedFileArchive":
        if settings.raw_archive_root is None:
            raise RawArchiveConfigurationError(
                "RAW_ARCHIVE_ROOT não configurado; a persistência deve falhar "
                "antes da base de dados"
            )
        return cls(settings.raw_archive_root)

    @staticmethod
    def storage_key(content_sha256: str) -> str:
        if len(content_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in content_sha256
        ):
            raise RawArchiveIntegrityError("SHA-256 inválido para arquivo")
        return f"sha256/{content_sha256[:2]}/{content_sha256}"

    def _target(self, *, storage_key: str, expected_sha256: str) -> Path:
        expected_key = self.storage_key(expected_sha256)
        if storage_key != expected_key:
            raise RawArchiveIntegrityError("A chave não corresponde ao SHA-256 esperado")
        parts = PurePosixPath(storage_key).parts
        if len(parts) != 3 or parts[0] != "sha256":
            raise RawArchiveIntegrityError("Chave de arquivo inválida")
        target = self.root.joinpath(*parts)
        resolved_parent = target.parent.resolve(strict=False)
        if not resolved_parent.is_relative_to(self.root):
            raise RawArchiveIntegrityError("A chave de arquivo sai da raiz configurada")
        return target

    @staticmethod
    def _make_private_directory(path: Path) -> None:
        if path.is_symlink():
            raise RawArchiveIntegrityError(
                "Um diretório controlado pelo arquivo não pode ser uma ligação simbólica"
            )
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Em Windows, ACLs prevalecem sobre os bits POSIX. Uma falha de chmod
        # não altera a raiz escolhida nem cria uma via de publicação.
        with suppress(OSError):
            path.chmod(0o700)

    @staticmethod
    def _hash_file(path: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        byte_size = 0
        with path.open("rb") as handle:
            for chunk in _chunks(handle):
                digest.update(chunk)
                byte_size += len(chunk)
        return digest.hexdigest(), byte_size

    def verify(
        self,
        *,
        storage_key: str,
        expected_sha256: str,
        expected_byte_size: int,
    ) -> RawArchiveVerification:
        target = self._target(
            storage_key=storage_key,
            expected_sha256=expected_sha256,
        )
        if target.is_symlink():
            return RawArchiveVerification(
                status="CORRUPT",
                storage_key=storage_key,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
                detail="O objeto é uma ligação simbólica e não foi seguido.",
            )
        if not target.exists():
            return RawArchiveVerification(
                status="UNAVAILABLE",
                storage_key=storage_key,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
                detail="Objeto bruto indisponível no arquivo configurado.",
            )
        try:
            mode = target.stat().st_mode
        except OSError:
            return RawArchiveVerification(
                status="UNAVAILABLE",
                storage_key=storage_key,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
                detail="Não foi possível consultar o objeto bruto.",
            )
        if not stat.S_ISREG(mode):
            return RawArchiveVerification(
                status="CORRUPT",
                storage_key=storage_key,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
                detail="A chave não referencia um ficheiro regular.",
            )

        try:
            observed_sha256, observed_byte_size = self._hash_file(target)
        except OSError:
            return RawArchiveVerification(
                status="UNAVAILABLE",
                storage_key=storage_key,
                expected_sha256=expected_sha256,
                expected_byte_size=expected_byte_size,
                detail="Não foi possível ler o objeto bruto para verificar a sua integridade.",
            )
        verified = observed_sha256 == expected_sha256 and observed_byte_size == expected_byte_size
        return RawArchiveVerification(
            status="VERIFIED" if verified else "CORRUPT",
            storage_key=storage_key,
            expected_sha256=expected_sha256,
            observed_sha256=observed_sha256,
            expected_byte_size=expected_byte_size,
            observed_byte_size=observed_byte_size,
            detail=(
                "O tamanho e o SHA-256 correspondem à atestação."
                if verified
                else "O tamanho ou o SHA-256 diverge da atestação; o objeto não é utilizável."
            ),
        )

    def archive(self, document: PrivateRawDocument) -> RawArchiveReceipt:
        storage_key = self.storage_key(document.content_sha256)
        target = self._target(
            storage_key=storage_key,
            expected_sha256=document.content_sha256,
        )
        if target.exists() or target.is_symlink():
            verification = self.verify(
                storage_key=storage_key,
                expected_sha256=document.content_sha256,
                expected_byte_size=len(document.content),
            )
            if verification.status != "VERIFIED":
                raise RawArchiveIntegrityError(verification.detail)
            return RawArchiveReceipt(
                storage_key=storage_key,
                content_sha256=document.content_sha256,
                byte_size=len(document.content),
                mime_type=document.mime_type,
                source_url=document.source_url,
                retrieved_at=document.retrieved_at,
                object_created=False,
            )

        # ``mkdir(parents=True)`` respeita o umask nos diretórios intermédios.
        # Reaplicamos explicitamente a política privada a cada nível criado pelo
        # arquivo, sem alterar diretórios exteriores à raiz configurada.
        self._make_private_directory(self.root)
        self._make_private_directory(self.root / "sha256")
        self._make_private_directory(target.parent)
        target = self._target(
            storage_key=storage_key,
            expected_sha256=document.content_sha256,
        )
        temporary = target.parent / f".{document.content_sha256}.{uuid.uuid4().hex}.tmp"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        descriptor = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(document.content)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, target)
                object_created = True
                with suppress(OSError):
                    target.chmod(0o600)
            except FileExistsError:
                verification = self.verify(
                    storage_key=storage_key,
                    expected_sha256=document.content_sha256,
                    expected_byte_size=len(document.content),
                )
                if verification.status != "VERIFIED":
                    raise RawArchiveIntegrityError(verification.detail) from None
                object_created = False
        finally:
            temporary.unlink(missing_ok=True)

        verification = self.verify(
            storage_key=storage_key,
            expected_sha256=document.content_sha256,
            expected_byte_size=len(document.content),
        )
        if verification.status != "VERIFIED":
            raise RawArchiveIntegrityError(verification.detail)
        return RawArchiveReceipt(
            storage_key=storage_key,
            content_sha256=document.content_sha256,
            byte_size=len(document.content),
            mime_type=document.mime_type,
            source_url=document.source_url,
            retrieved_at=document.retrieved_at,
            object_created=object_created,
        )
