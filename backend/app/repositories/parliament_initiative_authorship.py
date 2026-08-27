"""Persistência privada e append-only de autorias parlamentares individuais."""

import hashlib
import json
from datetime import UTC, datetime

from app.models.parliamentary_initiative_authorship import (
    PARLIAMENT_INITIATIVE_AUTHORSHIP_PARSER_VERSION,
    ParliamentInitiativeAuthorObservation,
    ParliamentInitiativeAuthorshipDataset,
)
from app.repositories.parliament_resource_normalization import (
    ParliamentResourceNormalizationRepository,
)

PARLIAMENT_INITIATIVE_AUTHORSHIP_SOURCE_NAME = "PARLIAMENT_INITIATIVE_AUTHORSHIP"


def _database_timestamp(value: datetime) -> datetime:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.replace(tzinfo=None)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _new_id(prefix: str, stable_value: str) -> str:
    return f"{prefix}_{hashlib.sha256(stable_value.encode('utf-8')).hexdigest()[:24]}"


def _observation_payload(
    observation: ParliamentInitiativeAuthorObservation,
) -> dict[str, object]:
    return observation.model_dump(mode="json")


def _observation_sha256(observation: ParliamentInitiativeAuthorObservation) -> str:
    return _sha256_json(_observation_payload(observation))


def _dataset_sha256(dataset: ParliamentInitiativeAuthorshipDataset) -> str:
    return _sha256_json(
        {
            "legislature": dataset.legislature,
            "parser_version": dataset.parser_version,
            "observations": [
                _observation_payload(observation) for observation in dataset.observations
            ],
        }
    )


class ParliamentInitiativeAuthorshipRepository(ParliamentResourceNormalizationRepository):
    """Guarda relações oficiais sem criar pessoa, caso editorial ou publicação."""

    async def persist_private_authorships(
        self,
        dataset: ParliamentInitiativeAuthorshipDataset,
        *,
        source_document_id: str,
    ) -> dict[str, object]:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        if dataset.parser_version != PARLIAMENT_INITIATIVE_AUTHORSHIP_PARSER_VERSION:
            raise ValueError("Versão do normalizador de autorias inválida")
        if dataset.raw_document is None:
            raise ValueError("Os bytes oficiais são obrigatórios")

        initiative_count = len(
            {observation.initiative_source_id for observation in dataset.observations}
        )
        deputy_count = len({observation.official_deputy_id for observation in dataset.observations})
        normalised_sha256 = _dataset_sha256(dataset)
        sync_id = await self._start_sync_run(
            source_name=PARLIAMENT_INITIATIVE_AUTHORSHIP_SOURCE_NAME,
            dataset_url=str(dataset.dataset_url),
            code_version=dataset.parser_version,
        )
        snapshot_id = ""
        snapshot_created = False
        observations_written = 0
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                source = await connection.fetchrow(
                    """
                    SELECT source.id, source.publisher::text AS publisher,
                           source.url, source.retrieved_at, source.content_sha256,
                           archived.storage_key, archived.byte_size,
                           archived.raw_content
                    FROM source_documents AS source
                    JOIN LATERAL (
                        SELECT archive.storage_key, archive.byte_size,
                               raw.content AS raw_content
                        FROM source_archive_attestations AS archive
                        JOIN raw_source_objects AS raw
                          ON raw.storage_key = archive.storage_key
                         AND raw.content_sha256 = archive.content_sha256
                        WHERE archive.source_document_id = source.id
                          AND archive.storage_backend = 'POSTGRES'
                          AND archive.content_sha256 = source.content_sha256
                          AND archive.retrieval_url = source.url
                          AND archive.retrieved_at = source.retrieved_at
                        ORDER BY archive.archived_at DESC, archive.id DESC
                        LIMIT 1
                    ) AS archived ON TRUE
                    WHERE source.id = $1
                    """,
                    source_document_id,
                )
                raw_content = bytes(source["raw_content"]) if source is not None else b""
                expected_storage_key = (
                    f"sha256/{dataset.document_sha256[:2]}/{dataset.document_sha256}"
                )
                if (
                    source is None
                    or str(source["publisher"]) != "PARLIAMENT"
                    or str(source["url"]) != str(dataset.dataset_url)
                    or source["retrieved_at"] != _database_timestamp(dataset.collected_at)
                    or str(source["content_sha256"]) != dataset.document_sha256
                    or str(source["storage_key"]) != expected_storage_key
                    or int(source["byte_size"]) != len(dataset.raw_document.content)
                    or raw_content != dataset.raw_document.content
                    or hashlib.sha256(raw_content).hexdigest() != dataset.document_sha256
                ):
                    raise ValueError("A fonte arquivada diverge da fotografia de autorias")

                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    (
                        "parliament-initiative-authorship:"
                        f"{source_document_id}:{dataset.legislature}:{dataset.parser_version}"
                    ),
                )
                snapshot_key = (
                    f"{source_document_id}|{dataset.legislature}|{dataset.parser_version}"
                )
                proposed_snapshot_id = _new_id(
                    "parliament_initiative_author_snapshot", snapshot_key
                )
                inserted_snapshot = await connection.fetchval(
                    """
                    INSERT INTO parliament_initiative_author_snapshots
                        (id, source_document_id, legislature, parser_version,
                         normalised_sha256, collected_at, initiative_count,
                         authorship_count, deputy_count, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                    ON CONFLICT (source_document_id, legislature, parser_version)
                    DO NOTHING
                    RETURNING id
                    """,
                    proposed_snapshot_id,
                    source_document_id,
                    dataset.legislature,
                    dataset.parser_version,
                    normalised_sha256,
                    _database_timestamp(dataset.collected_at),
                    initiative_count,
                    len(dataset.observations),
                    deputy_count,
                )
                snapshot = await connection.fetchrow(
                    """
                    SELECT id, normalised_sha256, collected_at, initiative_count,
                           authorship_count, deputy_count
                    FROM parliament_initiative_author_snapshots
                    WHERE source_document_id = $1
                      AND legislature = $2
                      AND parser_version = $3
                    """,
                    source_document_id,
                    dataset.legislature,
                    dataset.parser_version,
                )
                if snapshot is None:
                    raise RuntimeError("A fotografia privada de autorias não foi criada")
                expected_snapshot = (
                    normalised_sha256,
                    _database_timestamp(dataset.collected_at),
                    initiative_count,
                    len(dataset.observations),
                    deputy_count,
                )
                actual_snapshot = (
                    str(snapshot["normalised_sha256"]),
                    snapshot["collected_at"],
                    int(snapshot["initiative_count"]),
                    int(snapshot["authorship_count"]),
                    int(snapshot["deputy_count"]),
                )
                if actual_snapshot != expected_snapshot:
                    raise ValueError(
                        "O mesmo documento e parser produziram outro manifesto de autorias; "
                        "uma correção exige nova versão do parser"
                    )
                snapshot_id = str(snapshot["id"])
                snapshot_created = inserted_snapshot is not None

                expected_rows = [
                    (
                        observation.initiative_source_id,
                        observation.official_deputy_id,
                        observation.parliamentary_name,
                        observation.parliamentary_group_label,
                        observation.relation.value,
                        _observation_sha256(observation),
                    )
                    for observation in dataset.observations
                ]
                if snapshot_created:
                    await connection.executemany(
                        """
                        INSERT INTO parliament_initiative_author_observations
                            (id, snapshot_id, initiative_source_id,
                             official_deputy_id, parliamentary_name,
                             parliamentary_group_label, relation,
                             source_record_sha256, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                        """,
                        [
                            (
                                _new_id(
                                    "parliament_initiative_author_observation",
                                    (
                                        f"{snapshot_id}|{observation.initiative_source_id}|"
                                        f"{observation.official_deputy_id}"
                                    ),
                                ),
                                snapshot_id,
                                *row,
                            )
                            for observation, row in zip(
                                dataset.observations, expected_rows, strict=True
                            )
                        ],
                    )
                    observations_written = len(expected_rows)

                materialised = await connection.fetch(
                    """
                    SELECT initiative_source_id, official_deputy_id,
                           parliamentary_name, parliamentary_group_label,
                           relation, source_record_sha256
                    FROM parliament_initiative_author_observations
                    WHERE snapshot_id = $1
                    ORDER BY initiative_source_id COLLATE "C",
                             official_deputy_id COLLATE "C"
                    """,
                    snapshot_id,
                )
                actual_rows = [
                    (
                        str(row["initiative_source_id"]),
                        str(row["official_deputy_id"]),
                        str(row["parliamentary_name"]),
                        (
                            str(row["parliamentary_group_label"])
                            if row["parliamentary_group_label"] is not None
                            else None
                        ),
                        str(row["relation"]),
                        str(row["source_record_sha256"]),
                    )
                    for row in materialised
                ]
                if actual_rows != expected_rows:
                    raise ValueError("As relações materializadas divergem do manifesto append-only")

                if snapshot_created:
                    await connection.execute(
                        """
                        INSERT INTO audit_events
                            (id, entity_type, entity_id, action, actor_alias,
                             before_json, after_json, reason, created_at)
                        VALUES ($1, 'PARLIAMENT_INITIATIVE_AUTHOR_SNAPSHOT', $2,
                                'INGESTED', $3, NULL, $4::jsonb,
                                'Autorias oficiais preservadas; revisão humana e publicação '
                                'são separadas', NOW())
                        """,
                        _new_id("audit", f"{snapshot_id}|INGESTED"),
                        snapshot_id,
                        dataset.parser_version,
                        _canonical_json(
                            {
                                "source_document_id": source_document_id,
                                "source_sha256": dataset.document_sha256,
                                "normalised_sha256": normalised_sha256,
                                "legislature": dataset.legislature,
                                "initiative_count": initiative_count,
                                "authorship_count": len(dataset.observations),
                                "deputy_count": deputy_count,
                                "identity_rule": "EXACT_AR_IDCADASTRO_ONLY",
                                "publishable": False,
                            }
                        ),
                    )

            await self._finish_sync_run(
                sync_id,
                status_value="PARTIAL",
                records_read=len(dataset.observations),
                records_written=observations_written,
                warnings=[
                    *dataset.warnings,
                    "A fotografia permanece privada e não cria pessoas ou publicações.",
                ],
            )
        except Exception as exc:
            await self._finish_sync_run(
                sync_id,
                status_value="FAILED",
                records_read=len(dataset.observations),
                records_written=0,
                warnings=list(dataset.warnings),
                error_message=str(exc),
            )
            raise

        return {
            "sync_run_id": sync_id,
            "source_document_id": source_document_id,
            "normalised_snapshot_id": snapshot_id,
            "snapshot_created": snapshot_created,
            "initiative_count": initiative_count,
            "authorship_count": len(dataset.observations),
            "deputy_count": deputy_count,
            "observations_written": observations_written,
            "sync_status": "PARTIAL",
            "people_created": 0,
            "editorial_cases_created": 0,
            "publication_performed": False,
            "publishable": False,
        }
