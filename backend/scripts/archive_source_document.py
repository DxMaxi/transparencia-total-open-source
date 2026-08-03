"""Arquiva os bytes exatos de um SourceDocument existente exclusivamente em staging.

O comando não altera o SourceDocument, não cria revisão e não publica dados. A
escrita exige duas confirmações explícitas e ``ENVIRONMENT=staging``. O URL
efetivo e o SHA-256 têm de coincidir exatamente com a fonte já persistida.
"""

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime

from pydantic import HttpUrl

from app.core.config import Settings, get_settings
from app.models.archive import PrivateRawDocument
from app.repositories.postgres import PostgresRepository
from app.services.http import OfficialHttpClient
from app.services.raw_archive import ContentAddressedFileArchive


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-document-id", required=True)
    parser.add_argument("--actor", required=True, help="Pseudónimo auditável do operador")
    parser.add_argument("--persist-attestation", action="store_true")
    parser.add_argument("--confirm-staging", action="store_true")
    args = parser.parse_args()
    if not args.persist_attestation or not args.confirm_staging:
        parser.error(
            "o arquivo exige --persist-attestation e --confirm-staging; "
            "a omissão deve falhar antes de aceder à base de dados"
        )
    return args


def _maximum_bytes(settings: Settings, publisher: str) -> int:
    if publisher == "BASE_GOV":
        return settings.base_max_bytes
    if publisher == "PARLIAMENT":
        return settings.parlamento_votes_max_bytes
    return settings.source_max_bytes


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    if settings.environment != "staging":
        raise RuntimeError("O arquivo persistente só pode executar com ENVIRONMENT=staging")
    archive = ContentAddressedFileArchive.from_settings(settings)
    actor = str(args.actor).strip()
    if len(actor) < 3 or len(actor) > 200:
        raise ValueError("O pseudónimo auditável deve ter entre 3 e 200 caracteres")

    repository = PostgresRepository(settings)
    await repository.connect()
    try:
        source = await repository.get_source_document_for_archival(
            source_document_id=args.source_document_id,
        )
        async with OfficialHttpClient(settings) as http:
            response = await http.get(
                source["url"],
                max_bytes=_maximum_bytes(settings, str(source["publisher"])),
            )
        final_url = str(response.url)
        if final_url != source["url"]:
            raise ValueError(
                "O URL efetivo atual diverge do SourceDocument; deve ser criada nova versão"
            )
        retrieved_at = datetime.now(UTC)
        expected_sha256 = str(source["content_sha256"])
        observed_sha256 = hashlib.sha256(response.content).hexdigest()
        if observed_sha256 != expected_sha256:
            raise ValueError(
                "Os bytes atuais têm SHA-256 diferente; o documento histórico não foi arquivado"
            )
        raw_document = PrivateRawDocument(
            source_url=HttpUrl(final_url),
            retrieved_at=retrieved_at,
            content_sha256=expected_sha256,
            mime_type=response.headers.get("content-type") or source["mime_type"],
            content=response.content,
        )
        receipt = archive.archive(raw_document)
        attestation = await repository.attest_source_archive(
            source_document_id=args.source_document_id,
            receipt=receipt,
            archived_by=actor,
        )
    finally:
        await repository.close()

    print(
        json.dumps(
            {
                "source_document_id": args.source_document_id,
                "storage_backend": receipt.storage_backend,
                "storage_key": receipt.storage_key,
                "content_sha256": receipt.content_sha256,
                "byte_size": receipt.byte_size,
                "object_created": receipt.object_created,
                "attestation_id": attestation["id"],
                "attestation_created": attestation["created"],
                "publication_eligible": False,
                "publication_rule": (
                    "O arquivo e a atestação não criam revisão nem autorização de publicação."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    asyncio.run(run(arguments()))


if __name__ == "__main__":
    main()
