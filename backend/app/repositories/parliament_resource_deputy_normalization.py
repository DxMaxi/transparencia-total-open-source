"""Persistência append-only das observações privadas de deputados."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from app.models.parliamentary_people import ParliamentDeputyObservationDataset
from app.repositories.parliament_resource_normalization import (
    ParliamentResourceNormalizationRepository,
)

PARLIAMENT_HISTORICAL_DEPUTIES_PARSER_VERSION = "parliament-historical-deputies-v1"
PARLIAMENT_HISTORICAL_DEPUTIES_SOURCE_NAME = "PARLIAMENT_HISTORICAL_DEPUTIES"


def _database_timestamp(value: datetime) -> datetime:
    utc_value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return utc_value.replace(tzinfo=None)


def _new_id(prefix: str, stable_value: str) -> str:
    digest = hashlib.sha256(stable_value.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:24]}"


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _dataset_digest(dataset: ParliamentDeputyObservationDataset) -> str:
    canonical = {
        "legislature": dataset.legislature,
        "parser_version": dataset.parser_version,
        "observations": [
            item.model_dump(mode="json", exclude={"source"}) for item in dataset.observations
        ],
    }
    return hashlib.sha256(_canonical_json(canonical).encode("utf-8")).hexdigest()


def _nested_counts(dataset: ParliamentDeputyObservationDataset) -> tuple[int, int, int]:
    return (
        sum(len(item.parliamentary_groups) for item in dataset.observations),
        sum(len(item.mandate_situations) for item in dataset.observations),
        sum(len(item.offices) for item in dataset.observations),
    )


class ParliamentResourceDeputyNormalizationRepository(ParliamentResourceNormalizationRepository):
    """Acrescenta fotografias privadas sem criar pessoas, revisões ou publicações."""

    async def persist_private_deputy_observations(
        self,
        dataset: ParliamentDeputyObservationDataset,
        *,
        expected_source_document_id: str,
    ) -> dict[str, object]:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        if dataset.parser_version != PARLIAMENT_HISTORICAL_DEPUTIES_PARSER_VERSION:
            raise ValueError("Versão do normalizador histórico de deputados inválida")
        if not dataset.observations:
            raise ValueError("O lote histórico privado de deputados não pode estar vazio")

        group_count, situation_count, office_count = _nested_counts(dataset)
        records_read = len(dataset.observations) + group_count + situation_count + office_count
        sync_id = await self._start_sync_run(
            source_name=PARLIAMENT_HISTORICAL_DEPUTIES_SOURCE_NAME,
            dataset_url=str(dataset.dataset_url),
            code_version=dataset.parser_version,
        )
        observations_written = 0
        snapshot_created = False
        snapshot_id = ""
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                source = await connection.fetchrow(
                    """
                    SELECT source.id, source.publisher::text AS publisher,
                           source.url, source.content_sha256
                    FROM source_documents AS source
                    WHERE source.id = $1
                      AND source.url = $2
                      AND source.content_sha256 = $3
                      AND source.publisher = 'PARLIAMENT'
                      AND EXISTS (
                          SELECT 1
                          FROM source_archive_attestations AS archive
                          WHERE archive.source_document_id = source.id
                            AND archive.content_sha256 = source.content_sha256
                            AND archive.retrieval_url = source.url
                      )
                    FOR SHARE
                    """,
                    expected_source_document_id,
                    str(dataset.dataset_url),
                    dataset.document_sha256,
                )
                if source is None:
                    raise ValueError(
                        "A fotografia de deputados exige o documento parlamentar exato e atestado"
                    )

                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    (
                        "parliament-deputy-snapshot:"
                        f"{expected_source_document_id}:{dataset.legislature}:"
                        f"{dataset.parser_version}"
                    ),
                )
                snapshot_key = (
                    f"{expected_source_document_id}|{dataset.legislature}|{dataset.parser_version}"
                )
                proposed_snapshot_id = _new_id("parliament_deputy_snapshot", snapshot_key)
                normalised_sha256 = _dataset_digest(dataset)
                inserted_snapshot = await connection.fetchval(
                    """
                    INSERT INTO parliament_deputy_snapshots
                        (id, source_document_id, legislature, parser_version,
                         normalised_sha256, collected_at, deputy_count,
                         group_period_count, situation_period_count, office_period_count,
                         created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
                    ON CONFLICT (source_document_id, legislature, parser_version) DO NOTHING
                    RETURNING id
                    """,
                    proposed_snapshot_id,
                    expected_source_document_id,
                    dataset.legislature,
                    dataset.parser_version,
                    normalised_sha256,
                    _database_timestamp(dataset.collected_at),
                    len(dataset.observations),
                    group_count,
                    situation_count,
                    office_count,
                )
                snapshot = await connection.fetchrow(
                    """
                    SELECT id, normalised_sha256, deputy_count, group_period_count,
                           situation_period_count, office_period_count
                    FROM parliament_deputy_snapshots
                    WHERE source_document_id = $1
                      AND legislature = $2
                      AND parser_version = $3
                    """,
                    expected_source_document_id,
                    dataset.legislature,
                    dataset.parser_version,
                )
                if snapshot is None:
                    raise RuntimeError("Não foi possível criar a fotografia privada de deputados")
                expected_snapshot = (
                    normalised_sha256,
                    len(dataset.observations),
                    group_count,
                    situation_count,
                    office_count,
                )
                actual_snapshot = (
                    str(snapshot["normalised_sha256"]),
                    int(snapshot["deputy_count"]),
                    int(snapshot["group_period_count"]),
                    int(snapshot["situation_period_count"]),
                    int(snapshot["office_period_count"]),
                )
                if actual_snapshot != expected_snapshot:
                    raise ValueError(
                        "O mesmo documento e parser produziram outra fotografia de deputados; "
                        "a correção exige uma nova versão do parser"
                    )
                snapshot_id = str(snapshot["id"])
                snapshot_created = inserted_snapshot is not None

                before_count = int(
                    await connection.fetchval(
                        """
                        SELECT COUNT(*) FROM parliament_deputy_observations
                        WHERE snapshot_id = $1
                        """,
                        snapshot_id,
                    )
                )
                rows: list[tuple[Any, ...]] = []
                for observation in dataset.observations:
                    groups = [
                        item.model_dump(mode="json") for item in observation.parliamentary_groups
                    ]
                    situations = [
                        item.model_dump(mode="json") for item in observation.mandate_situations
                    ]
                    offices = [item.model_dump(mode="json") for item in observation.offices]
                    rows.append(
                        (
                            _new_id(
                                "parliament_deputy_observation",
                                f"{snapshot_id}|{observation.source_id}",
                            ),
                            snapshot_id,
                            observation.source_id,
                            observation.candidate_source_id,
                            observation.parliamentary_name,
                            observation.full_name,
                            observation.constituency_source_id,
                            observation.constituency_label,
                            _canonical_json(groups),
                            _canonical_json(situations),
                            _canonical_json(offices),
                        )
                    )
                await connection.executemany(
                    """
                    INSERT INTO parliament_deputy_observations
                        (id, snapshot_id, source_id, candidate_source_id,
                         parliamentary_name, full_name, constituency_source_id,
                         constituency_label, parliamentary_groups,
                         mandate_situations, offices, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8,
                            $9::jsonb, $10::jsonb, $11::jsonb, NOW())
                    ON CONFLICT (source_id, snapshot_id) DO NOTHING
                    """,
                    rows,
                )
                materialised = await connection.fetchrow(
                    """
                    SELECT COUNT(*) AS deputy_count,
                           COALESCE(SUM(jsonb_array_length(parliamentary_groups)), 0)
                               AS group_period_count,
                           COALESCE(SUM(jsonb_array_length(mandate_situations)), 0)
                               AS situation_period_count,
                           COALESCE(SUM(jsonb_array_length(offices)), 0)
                               AS office_period_count
                    FROM parliament_deputy_observations
                    WHERE snapshot_id = $1
                    """,
                    snapshot_id,
                )
                if materialised is None:
                    raise RuntimeError("A fotografia de deputados não foi materializada")
                actual_materialised = (
                    int(materialised["deputy_count"]),
                    int(materialised["group_period_count"]),
                    int(materialised["situation_period_count"]),
                    int(materialised["office_period_count"]),
                )
                expected_materialised = (
                    len(dataset.observations),
                    group_count,
                    situation_count,
                    office_count,
                )
                if actual_materialised != expected_materialised:
                    raise RuntimeError(
                        "A materialização de deputados diverge do manifesto imutável"
                    )
                observations_written = actual_materialised[0] - before_count

                if snapshot_created:
                    after = {
                        "source_document_id": expected_source_document_id,
                        "source_sha256": dataset.document_sha256,
                        "normalised_sha256": normalised_sha256,
                        "legislature": dataset.legislature,
                        "parser_version": dataset.parser_version,
                        "deputy_count": len(dataset.observations),
                        "group_period_count": group_count,
                        "situation_period_count": situation_count,
                        "office_period_count": office_count,
                        "publishable": False,
                    }
                    await connection.execute(
                        """
                        INSERT INTO audit_events
                            (id, entity_type, entity_id, action, actor_alias,
                             before_json, after_json, reason, created_at)
                        VALUES ($1, 'PARLIAMENT_DEPUTY_SNAPSHOT', $2, 'INGESTED', $3,
                                NULL, $4::jsonb,
                                'Observações oficiais preservadas; publicação exige revisão humana',
                                NOW())
                        """,
                        _new_id("audit", f"{snapshot_id}|INGESTED"),
                        snapshot_id,
                        dataset.parser_version,
                        _canonical_json(after),
                    )

            await self._finish_sync_run(
                sync_id,
                status_value="PARTIAL",
                records_read=records_read,
                records_written=observations_written,
                warnings=list(dataset.warnings),
            )
        except Exception as exc:
            await self._finish_sync_run(
                sync_id,
                status_value="FAILED",
                records_read=records_read,
                records_written=0,
                warnings=list(dataset.warnings),
                error_message=str(exc),
            )
            raise

        return {
            "sync_run_id": sync_id,
            "source_document_id": expected_source_document_id,
            "normalised_snapshot_id": snapshot_id,
            "snapshot_created": snapshot_created,
            "deputy_count": len(dataset.observations),
            "group_period_count": group_count,
            "situation_period_count": situation_count,
            "office_period_count": office_count,
            "observations_written": observations_written,
            "sync_status": "PARTIAL",
            "publishable": False,
        }
