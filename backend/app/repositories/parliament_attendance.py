"""Persistência privada e append-only de fotografias oficiais de presenças."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from app.models.parliamentary_attendance import (
    ParliamentAttendanceDataset,
    ParliamentAttendanceObservation,
    ParliamentAttendanceStatus,
)
from app.repositories.official_index_staging import OfficialIndexStagingRepository


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


def _observation_payload(observation: ParliamentAttendanceObservation) -> dict[str, object]:
    return observation.model_dump(mode="json")


def _observation_digest(observation: ParliamentAttendanceObservation) -> str:
    return hashlib.sha256(
        _canonical_json(_observation_payload(observation)).encode("utf-8")
    ).hexdigest()


def _dataset_digest(dataset: ParliamentAttendanceDataset) -> str:
    canonical = {
        "legislature": dataset.legislature,
        "official_meeting_id": dataset.official_meeting_id,
        "meeting_date": dataset.meeting_date.isoformat(),
        "meeting_type": dataset.meeting_type,
        "session_number": dataset.session_number,
        "parser_version": dataset.parser_version,
        "observations": [_observation_payload(item) for item in dataset.observations],
    }
    return hashlib.sha256(_canonical_json(canonical).encode("utf-8")).hexdigest()


def _status_counts(dataset: ParliamentAttendanceDataset) -> dict[str, int]:
    return {
        status.value: sum(item.status is status for item in dataset.observations)
        for status in ParliamentAttendanceStatus
    }


class ParliamentAttendanceRepository(OfficialIndexStagingRepository):
    """Guarda uma reunião completa sem criar casos, pessoas ou projeções públicas."""

    async def persist_private_attendance(
        self,
        dataset: ParliamentAttendanceDataset,
    ) -> dict[str, object]:
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        if dataset.raw_document is None:
            raise ValueError("Os bytes oficiais são obrigatórios para persistir presenças")
        if dataset.raw_document.content_sha256 != dataset.document_sha256:
            raise ValueError("O documento de presenças diverge do SHA-256 declarado")

        receipt = await self.archive_raw_document(raw_document=dataset.raw_document)
        sync_id = await self._start_sync_run(
            source_name="PARLIAMENT_PLENARY_ATTENDANCE",
            dataset_url=str(dataset.source_url),
            code_version=dataset.parser_version,
        )
        records_written = 0
        snapshot_created = False
        attestation_created = False
        source_document_id = ""
        snapshot_id = ""
        counts = _status_counts(dataset)
        normalised_sha256 = _dataset_digest(dataset)
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                source_key = f"{dataset.source_url}|{dataset.document_sha256}"
                proposed_source_id = _new_id("source", source_key)
                proposed_official_id = (
                    f"AR-PLENARY-{dataset.legislature}-{dataset.official_meeting_id}"
                )
                inserted_source = await connection.fetchrow(
                    """
                    INSERT INTO source_documents
                        (id, publisher, kind, title, official_identifier, url,
                         retrieved_at, published_at, content_sha256, mime_type,
                         parser_version, created_at)
                    VALUES ($1, 'PARLIAMENT', 'ATTENDANCE', $2, $3, $4,
                            $5, $6, $7, $8, $9, NOW())
                    ON CONFLICT (url, content_sha256) DO NOTHING
                    RETURNING id
                    """,
                    proposed_source_id,
                    (
                        "Presenças à reunião plenária de "
                        f"{dataset.meeting_date.isoformat()} — {dataset.legislature}"
                    ),
                    proposed_official_id,
                    str(dataset.source_url),
                    _database_timestamp(dataset.collected_at),
                    datetime.combine(dataset.meeting_date, datetime.min.time()),
                    dataset.document_sha256,
                    dataset.raw_document.mime_type,
                    dataset.parser_version,
                )
                source = inserted_source
                if source is None:
                    source = await connection.fetchrow(
                        """
                        SELECT id, publisher::text AS publisher, kind::text AS kind,
                               official_identifier, url, content_sha256
                        FROM source_documents
                        WHERE url = $1 AND content_sha256 = $2
                        """,
                        str(dataset.source_url),
                        dataset.document_sha256,
                    )
                else:
                    source = await connection.fetchrow(
                        """
                        SELECT id, publisher::text AS publisher, kind::text AS kind,
                               official_identifier, url, content_sha256
                        FROM source_documents WHERE id = $1
                        """,
                        str(inserted_source["id"]),
                    )
                if source is None:
                    raise RuntimeError("Não foi possível registar a fonte oficial de presenças")
                if (
                    str(source["publisher"]) != "PARLIAMENT"
                    or str(source["kind"]) != "ATTENDANCE"
                    or str(source["official_identifier"]) != proposed_official_id
                    or str(source["url"]) != str(dataset.source_url)
                    or str(source["content_sha256"]) != dataset.document_sha256
                ):
                    raise ValueError("O SourceDocument existente diverge da reunião oficial")
                source_document_id = str(source["id"])

                attestation = await self._attest_source_archive(
                    connection,
                    source_document_id=source_document_id,
                    receipt=receipt,
                    archived_by=f"sync:{dataset.parser_version}",
                )
                attestation_created = bool(attestation["created"])

                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    (
                        "parliament-attendance-snapshot:"
                        f"{source_document_id}:{dataset.legislature}:{dataset.parser_version}"
                    ),
                )
                snapshot_key = (
                    f"{source_document_id}|{dataset.legislature}|{dataset.parser_version}"
                )
                proposed_snapshot_id = _new_id("parliament_attendance_snapshot", snapshot_key)
                inserted_snapshot = await connection.fetchval(
                    """
                    INSERT INTO parliament_attendance_snapshots
                        (id, source_document_id, legislature, official_meeting_id,
                         meeting_date, meeting_type, session_number, parser_version,
                         normalised_sha256, collected_at, record_count, present_count,
                         justified_absence_count, unjustified_absence_count,
                         unknown_count, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                            $11, $12, $13, $14, $15, NOW())
                    ON CONFLICT (source_document_id, legislature, parser_version) DO NOTHING
                    RETURNING id
                    """,
                    proposed_snapshot_id,
                    source_document_id,
                    dataset.legislature,
                    dataset.official_meeting_id,
                    dataset.meeting_date,
                    dataset.meeting_type,
                    dataset.session_number,
                    dataset.parser_version,
                    normalised_sha256,
                    _database_timestamp(dataset.collected_at),
                    len(dataset.observations),
                    counts[ParliamentAttendanceStatus.PRESENT.value],
                    counts[ParliamentAttendanceStatus.JUSTIFIED_ABSENCE.value],
                    counts[ParliamentAttendanceStatus.UNJUSTIFIED_ABSENCE.value],
                    counts[ParliamentAttendanceStatus.UNKNOWN.value],
                )
                snapshot = await connection.fetchrow(
                    """
                    SELECT id, official_meeting_id, meeting_date, meeting_type,
                           session_number, normalised_sha256, record_count,
                           present_count, justified_absence_count,
                           unjustified_absence_count, unknown_count
                    FROM parliament_attendance_snapshots
                    WHERE source_document_id = $1
                      AND legislature = $2
                      AND parser_version = $3
                    """,
                    source_document_id,
                    dataset.legislature,
                    dataset.parser_version,
                )
                if snapshot is None:
                    raise RuntimeError("A fotografia privada de presenças não foi criada")
                expected_snapshot = (
                    dataset.official_meeting_id,
                    dataset.meeting_date,
                    dataset.meeting_type,
                    dataset.session_number,
                    normalised_sha256,
                    len(dataset.observations),
                    counts[ParliamentAttendanceStatus.PRESENT.value],
                    counts[ParliamentAttendanceStatus.JUSTIFIED_ABSENCE.value],
                    counts[ParliamentAttendanceStatus.UNJUSTIFIED_ABSENCE.value],
                    counts[ParliamentAttendanceStatus.UNKNOWN.value],
                )
                actual_snapshot = (
                    str(snapshot["official_meeting_id"]),
                    snapshot["meeting_date"],
                    str(snapshot["meeting_type"]),
                    str(snapshot["session_number"])
                    if snapshot["session_number"] is not None
                    else None,
                    str(snapshot["normalised_sha256"]),
                    int(snapshot["record_count"]),
                    int(snapshot["present_count"]),
                    int(snapshot["justified_absence_count"]),
                    int(snapshot["unjustified_absence_count"]),
                    int(snapshot["unknown_count"]),
                )
                if actual_snapshot != expected_snapshot:
                    raise ValueError(
                        "O mesmo documento e parser produziram outra fotografia de presenças; "
                        "uma correção exige nova versão do parser"
                    )
                snapshot_id = str(snapshot["id"])
                snapshot_created = inserted_snapshot is not None

                before_count = int(
                    await connection.fetchval(
                        "SELECT COUNT(*) FROM parliament_attendance_observations "
                        "WHERE snapshot_id = $1",
                        snapshot_id,
                    )
                )
                rows: list[tuple[Any, ...]] = []
                for observation in dataset.observations:
                    record_sha256 = _observation_digest(observation)
                    rows.append(
                        (
                            _new_id(
                                "parliament_attendance_observation",
                                f"{snapshot_id}|{observation.official_deputy_id}",
                            ),
                            snapshot_id,
                            observation.official_deputy_id,
                            observation.parliamentary_name,
                            observation.parliamentary_group_label,
                            observation.status.value,
                            observation.source_status_label,
                            observation.source_status_code,
                            observation.absence_reason,
                            record_sha256,
                        )
                    )
                await connection.executemany(
                    """
                    INSERT INTO parliament_attendance_observations
                        (id, snapshot_id, official_deputy_id, parliamentary_name,
                         parliamentary_group_label, status, source_status_label,
                         source_status_code, absence_reason, source_record_sha256,
                         created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
                    ON CONFLICT (snapshot_id, official_deputy_id) DO NOTHING
                    """,
                    rows,
                )
                materialised = await connection.fetchrow(
                    """
                    SELECT COUNT(*)::int AS record_count,
                           COUNT(*) FILTER (WHERE status = 'PRESENT')::int AS present_count,
                           COUNT(*) FILTER (
                               WHERE status = 'JUSTIFIED_ABSENCE'
                           )::int AS justified_absence_count,
                           COUNT(*) FILTER (
                               WHERE status = 'UNJUSTIFIED_ABSENCE'
                           )::int AS unjustified_absence_count,
                           COUNT(*) FILTER (WHERE status = 'UNKNOWN')::int AS unknown_count
                    FROM parliament_attendance_observations
                    WHERE snapshot_id = $1
                    """,
                    snapshot_id,
                )
                if materialised is None:
                    raise RuntimeError("As observações privadas de presenças não foram criadas")
                actual_counts = (
                    int(materialised["record_count"]),
                    int(materialised["present_count"]),
                    int(materialised["justified_absence_count"]),
                    int(materialised["unjustified_absence_count"]),
                    int(materialised["unknown_count"]),
                )
                expected_counts = (
                    len(dataset.observations),
                    counts[ParliamentAttendanceStatus.PRESENT.value],
                    counts[ParliamentAttendanceStatus.JUSTIFIED_ABSENCE.value],
                    counts[ParliamentAttendanceStatus.UNJUSTIFIED_ABSENCE.value],
                    counts[ParliamentAttendanceStatus.UNKNOWN.value],
                )
                if actual_counts != expected_counts:
                    raise RuntimeError("As presenças materializadas divergem do manifesto imutável")
                records_written = actual_counts[0] - before_count

                if snapshot_created:
                    after = {
                        "source_document_id": source_document_id,
                        "source_sha256": dataset.document_sha256,
                        "normalised_sha256": normalised_sha256,
                        "legislature": dataset.legislature,
                        "official_meeting_id": dataset.official_meeting_id,
                        "meeting_date": dataset.meeting_date.isoformat(),
                        "record_count": len(dataset.observations),
                        "status_counts": counts,
                        "publishable": False,
                    }
                    await connection.execute(
                        """
                        INSERT INTO audit_events
                            (id, entity_type, entity_id, action, actor_alias,
                             before_json, after_json, reason, created_at)
                        VALUES ($1, 'PARLIAMENT_ATTENDANCE_SNAPSHOT', $2, 'INGESTED',
                                $3, NULL, $4::jsonb,
                                'Reunião oficial preservada; revisão humana e publicação '
                                'são separadas',
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
                records_read=len(dataset.observations),
                records_written=records_written,
                warnings=[
                    *dataset.warnings,
                    "A reunião permanece privada e sem qualquer caso editorial ou publicação.",
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
            "archive_object_created": receipt.object_created,
            "archive_attestation_created": attestation_created,
            "record_count": len(dataset.observations),
            "present_count": counts[ParliamentAttendanceStatus.PRESENT.value],
            "justified_absence_count": counts[ParliamentAttendanceStatus.JUSTIFIED_ABSENCE.value],
            "unjustified_absence_count": counts[
                ParliamentAttendanceStatus.UNJUSTIFIED_ABSENCE.value
            ],
            "unknown_count": counts[ParliamentAttendanceStatus.UNKNOWN.value],
            "observations_written": records_written,
            "sync_status": "PARTIAL",
            "publishable": False,
        }
