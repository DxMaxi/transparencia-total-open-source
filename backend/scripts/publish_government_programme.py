"""Arquiva e publica o catálogo inicial do Programa do XXV Governo.

O estado UNVERIFIED significa apenas que o compromisso existe no programa. Não
é uma avaliação de execução. Qualquer outro estado continua a exigir prova
oficial adicional e revisão humana.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.models.archive import PrivateRawDocument
from app.repositories.official_index_staging import OfficialIndexStagingRepository
from app.services.http import OfficialHttpClient

CATALOGUE_PATH = Path(__file__).resolve().parents[2] / "data" / "xxv-government-programme.json"
CODE_VERSION = "government-programme-catalogue-v1"
SOURCE_NAME = "GOVERNMENT_PROGRAMME_XXV"
REVIEWER_ALIAS = "programme-catalogue-v4"
REVIEW_RATIONALE = (
    "Transcrição editorial confirmada contra o Programa do XXV Governo; "
    "o estado UNVERIFIED não avalia a execução."
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def load_catalogue() -> dict[str, Any]:
    catalogue = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    commitments = catalogue.get("commitments")
    if not isinstance(commitments, list) or not commitments:
        raise ValueError("O catálogo oficial não contém compromissos")
    stable_keys = [item.get("stableKey") for item in commitments if isinstance(item, dict)]
    if len(stable_keys) != len(commitments) or len(set(stable_keys)) != len(stable_keys):
        raise ValueError("As chaves dos compromissos têm de ser únicas")
    return catalogue


async def publish() -> None:
    settings = get_settings()
    if settings.environment != "production":
        raise RuntimeError("A publicação do programa só pode correr em production")
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL não configurada")

    catalogue = load_catalogue()
    source_url = str(catalogue["sourceUrl"])
    expected_sha256 = str(catalogue["sourceSha256"])
    expected_byte_size = int(catalogue["sourceByteSize"])
    commitments = catalogue["commitments"]

    repository = OfficialIndexStagingRepository(settings)
    await repository.connect()
    sync_id = await repository._start_sync_run(  # noqa: SLF001
        source_name=SOURCE_NAME,
        dataset_url=source_url,
        code_version=CODE_VERSION,
    )
    try:
        async with OfficialHttpClient(settings) as http:
            response = await http.get(source_url, max_bytes=10_000_000)
        retrieved_at = datetime.now(UTC)
        content_sha256 = hashlib.sha256(response.content).hexdigest()
        raw_document = PrivateRawDocument(
            source_url=str(response.url),
            retrieved_at=retrieved_at,
            content_sha256=content_sha256,
            mime_type=response.headers.get("content-type"),
            content=response.content,
        )
        receipt = await repository.archive_raw_document(raw_document=raw_document)

        if content_sha256 != expected_sha256 or len(response.content) != expected_byte_size:
            raise RuntimeError(
                "O Programa do Governo mudou. Os novos bytes foram arquivados, mas "
                "a publicação exige revisão e atualização explícita do catálogo."
            )
        if repository.pool is None:
            raise RuntimeError("Base de dados não configurada")

        created = 0
        async with repository.pool.acquire() as connection, connection.transaction():
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                "government-programme-xxv-publication",
            )
            source_document_id = await repository._ensure_source_document(  # noqa: SLF001
                connection,
                publisher="OTHER_OFFICIAL",
                kind="GOVERNMENT_PROGRAMME",
                title=str(catalogue["title"]),
                url=str(raw_document.source_url),
                retrieved_at=raw_document.retrieved_at,
                content_sha256=content_sha256,
                mime_type=raw_document.mime_type,
                parser_version=CODE_VERSION,
            )
            await repository._attest_source_archive(  # noqa: SLF001
                connection,
                source_document_id=source_document_id,
                receipt=receipt,
                archived_by=f"sync:{CODE_VERSION}",
            )

            programme_id = await connection.fetchval(
                """
                INSERT INTO government_programmes
                    (id, government_number, title, source_document_id, created_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (government_number, title) DO NOTHING
                RETURNING id
                """,
                _new_id("government_programme"),
                catalogue["governmentNumber"],
                catalogue["title"],
                source_document_id,
            )
            if programme_id is None:
                existing_programme = await connection.fetchrow(
                    """
                    SELECT id, source_document_id
                    FROM government_programmes
                    WHERE government_number = $1 AND title = $2
                    """,
                    catalogue["governmentNumber"],
                    catalogue["title"],
                )
                if existing_programme is None:
                    raise RuntimeError("Não foi possível recuperar o programa existente")
                if str(existing_programme["source_document_id"]) != source_document_id:
                    raise RuntimeError("O programa existente aponta para outra versão documental")
                programme_id = str(existing_programme["id"])

            for item in commitments:
                promise_id = await connection.fetchval(
                    """
                    INSERT INTO promises
                        (id, programme_id, stable_key, title, description, area,
                         programme_page, status, progress, rationale,
                         methodology_version, last_reviewed_at, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $4, $5, $6, 'UNVERIFIED', 0,
                            $7, $8, NOW(), NOW(), NOW())
                    ON CONFLICT (stable_key) DO NOTHING
                    RETURNING id
                    """,
                    _new_id("promise"),
                    programme_id,
                    item["stableKey"],
                    item["title"],
                    item["area"],
                    item["programmePage"],
                    (
                        "Compromisso localizado no programa oficial. O estado de execução "
                        "ainda não foi avaliado porque não existe prova oficial de "
                        "implementação associada."
                    ),
                    catalogue["methodologyVersion"],
                )
                if promise_id is None:
                    existing = await connection.fetchrow(
                        """
                        SELECT id, programme_id, title, area, programme_page
                        FROM promises WHERE stable_key = $1
                        """,
                        item["stableKey"],
                    )
                    if existing is None:
                        raise RuntimeError("Compromisso existente não recuperável")
                    expected = (
                        str(programme_id),
                        item["title"],
                        item["area"],
                        item["programmePage"],
                    )
                    observed = (
                        str(existing["programme_id"]),
                        str(existing["title"]),
                        str(existing["area"]),
                        str(existing["programme_page"]),
                    )
                    if observed != expected:
                        raise RuntimeError(
                            f"O compromisso {item['stableKey']} diverge do catálogo revisto"
                        )
                    promise_id = str(existing["id"])
                else:
                    created += 1

                latest_decision = await connection.fetchval(
                    """
                    SELECT decision::text FROM promise_reviews
                    WHERE promise_id = $1
                    ORDER BY reviewed_at DESC, id DESC LIMIT 1
                    """,
                    promise_id,
                )
                if latest_decision is None:
                    await connection.execute(
                        """
                        INSERT INTO promise_reviews
                            (id, promise_id, previous_status, proposed_status, decision,
                             reviewer_alias, rationale, source_document_id, reviewed_at)
                        VALUES ($1, $2, 'UNVERIFIED', 'UNVERIFIED', 'ACCEPT',
                                $3, $4, $5, NOW())
                        """,
                        _new_id("promise_review"),
                        promise_id,
                        REVIEWER_ALIAS,
                        REVIEW_RATIONALE,
                        source_document_id,
                    )

        await repository._finish_sync_run(  # noqa: SLF001
            sync_id,
            status_value="SUCCEEDED",
            records_read=len(commitments),
            records_written=len(commitments),
            warnings=[
                "Todos os compromissos permanecem UNVERIFIED até existir prova oficial de execução."
            ],
        )
        print(
            json.dumps(
                {
                    "status": "PUBLISHED",
                    "catalogued": len(commitments),
                    "created": created,
                    "source_sha256": content_sha256,
                },
                ensure_ascii=False,
            )
        )
    except Exception as exc:
        await repository._finish_sync_run(  # noqa: SLF001
            sync_id,
            status_value="FAILED",
            records_read=0,
            records_written=0,
            warnings=[],
            error_message=str(exc),
        )
        raise
    finally:
        await repository.close()


def main() -> None:
    asyncio.run(publish())


if __name__ == "__main__":
    main()
