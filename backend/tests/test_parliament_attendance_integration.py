import hashlib
import os
import uuid
from datetime import UTC, datetime

import asyncpg
import pytest

from app.core.config import Settings
from app.models.archive import PrivateRawDocument
from app.models.editorial import (
    EditorialAction,
    PoliticianAttendanceEditorialProposalRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.editorial import EditorialRepository
from app.repositories.parliament_attendance import ParliamentAttendanceRepository
from app.repositories.politician_attendance_editorial import (
    PoliticianAttendanceEditorialRepository,
)
from app.services.parliament_attendance import (
    ParliamentAttendanceNormalizer,
    ParliamentAttendanceStager,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="Teste de integração real: exige DATABASE_URL para PostgreSQL descartável",
)


async def _prepare_disposable_auth_user(
    connection: asyncpg.Connection,
    auth_user_id: uuid.UUID,
) -> None:
    if not await connection.fetchval("SELECT to_regclass('auth.users') IS NOT NULL"):
        return
    if not await connection.fetchval(
        "SELECT to_regclass('auth.tt_disposable_test_marker') IS NOT NULL"
    ):
        pytest.skip("A FK auth.users só é exercitada numa base descartável identificada")
    await connection.execute(
        "INSERT INTO auth.users (id) VALUES ($1) ON CONFLICT (id) DO NOTHING",
        auth_user_id,
    )


def _html(*, deputy_seed: int) -> bytes:
    rows: list[str] = []
    for index in range(100):
        status = "Falta Justificada (FJ)" if index == 0 else "Presença (P)"
        reason = "<td>Motivo Missão parlamentar</td>" if index == 0 else "<td></td>"
        rows.append(
            "<tr><td>Deputado "
            f'<a href="/DeputadoGP/Paginas/Biografia.aspx?BID={deputy_seed + index}">'
            f"Pessoa Integração {index:03d}</a></td>"
            "<td>Grupo Parlamentar/Partido TESTE</td>"
            f"<td>Presença/Falta {status}</td>{reason}</tr>"
        )
    return (
        "<html><body><h1>Reunião Plenária Ordinária de 2026-07-17.</h1><table>"
        + "".join(rows)
        + "</table>"
        '<a href="https://app.parlamento.pt/webutils/docs/doc.pdf?'
        'Fich=XVII_1_111_2026-07-17.pdf&amp;Inline=true">PDF</a>'
        "</body></html>"
    ).encode()


@pytest.fixture
async def repository() -> ParliamentAttendanceRepository:
    repo = ParliamentAttendanceRepository(Settings(environment="test"))
    await repo.connect()
    try:
        yield repo
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_attendance_snapshot_and_case_are_private_append_only_and_idempotent(
    repository: ParliamentAttendanceRepository,
) -> None:
    assert repository.pool is not None
    unique_number = int(uuid.uuid4().hex[:12], 16)
    meeting_bid = str(100_000_000_000 + unique_number % 800_000_000_000)
    deputy_seed = 8_000_000_000 + unique_number % 1_000_000_000
    source_url = (
        "https://www.parlamento.pt/DeputadoGP/Paginas/"
        f"DetalheReuniaoPlenaria.aspx?BID={meeting_bid}"
    )
    content = _html(deputy_seed=deputy_seed)
    content_sha256 = hashlib.sha256(content).hexdigest()
    raw_document = PrivateRawDocument(
        source_url=source_url,
        retrieved_at=datetime.now(UTC).replace(microsecond=0),
        content_sha256=content_sha256,
        mime_type="text/html",
        content=content,
    )
    dataset = ParliamentAttendanceNormalizer().normalise(
        raw_document,
        legislature="XVII",
    )

    before_sessions: int
    before_public_attendance: int
    async with repository.pool.acquire() as connection:
        before_sessions = int(
            await connection.fetchval("SELECT COUNT(*) FROM parliamentary_sessions")
        )
        before_public_attendance = int(
            await connection.fetchval("SELECT COUNT(*) FROM attendance_records")
        )

    stored = await ParliamentAttendanceStager(
        Settings(environment="test"),
        repository,
    ).store(dataset)
    repeated = await ParliamentAttendanceStager(
        Settings(environment="test"),
        repository,
    ).store(dataset)
    snapshot_id = str(stored["normalised_snapshot_id"])
    source_document_id = str(stored["source_document_id"])
    assert stored["snapshot_created"] is True
    assert repeated["snapshot_created"] is False
    assert repeated["observations_written"] == 0
    assert stored["record_count"] == 100
    assert stored["present_count"] == 99
    assert stored["justified_absence_count"] == 1
    assert stored["unknown_count"] == 0
    assert stored["editorial_cases_created"] == 0
    assert stored["publication_performed"] is False

    staff_id = f"staff_attendance_{uuid.uuid4().hex}"
    auth_user_id = uuid.uuid4()
    alias = f"revisor-attendance-{uuid.uuid4().hex[:12]}"
    async with repository.pool.acquire() as connection, connection.transaction():
        await _prepare_disposable_auth_user(connection, auth_user_id)
        await connection.execute(
            """
            INSERT INTO staff_profiles
                (id, auth_user_id, public_alias, role, active, created_at, updated_at)
            VALUES ($1, $2, $3, 'REVIEWER', TRUE, NOW(), NOW())
            """,
            staff_id,
            auth_user_id,
            alias,
        )

    actor = StaffSession(
        staff_id=staff_id,
        auth_user_id=auth_user_id,
        public_alias=alias,
        role=StaffRole.REVIEWER,
        assurance_level="aal1",
        mfa_required=False,
    )
    adapter = PoliticianAttendanceEditorialRepository(repository.pool)
    candidates = await adapter.list_candidates(legislature="XVII", limit=20, offset=0)
    candidate = next(item for item in candidates["items"] if item["snapshot_id"] == snapshot_id)
    assert candidate["proposal_eligible"] is True
    assert candidate["publication_ready"] is False
    assert candidate["identity_reconciliation"]["exact_identities"] == 0
    assert candidate["selective_processing_allowed"] is False

    payload = PoliticianAttendanceEditorialProposalRequest(
        snapshot_id=snapshot_id,
        confirm_private_only=True,
        confirm_complete_meeting=True,
        confirm_exact_official_ids_only=True,
        confirm_no_name_matching=True,
        confirm_absence_is_not_noncompliance=True,
        confirm_no_selective_processing=True,
    )
    created = await adapter.create_proposal(payload=payload, actor=actor)
    repeated_case = await adapter.create_proposal(payload=payload, actor=actor)
    assert created["created"] is True
    assert repeated_case["created"] is False
    assert repeated_case["case"]["id"] == created["case"]["id"]
    assert created["case"]["subject_type"] == "PARLIAMENT_ATTENDANCE_SNAPSHOT"
    assert created["case"]["current_state"] == "PENDING"
    assert created["attendance_records_created"] == 0
    assert created["publication_performed"] is False

    case_id = str(created["case"]["id"])
    editorial = EditorialRepository(repository.pool)
    await editorial.transition(
        case_id=case_id,
        action=EditorialAction.START_REVIEW,
        expected_revision=1,
        rationale="A reunião integral será comparada com a fonte e todos os BID oficiais.",
        source_confirmed=False,
        actor=actor,
    )
    await editorial.transition(
        case_id=case_id,
        action=EditorialAction.APPROVE,
        expected_revision=2,
        rationale="A fonte, o arquivo, as contagens e os estados individuais foram revistos.",
        source_confirmed=True,
        actor=actor,
    )

    async with repository.pool.acquire() as connection:
        after_sessions = int(
            await connection.fetchval("SELECT COUNT(*) FROM parliamentary_sessions")
        )
        after_public_attendance = int(
            await connection.fetchval("SELECT COUNT(*) FROM attendance_records")
        )
        publication_events = int(
            await connection.fetchval(
                "SELECT COUNT(*) FROM editorial_publication_events WHERE case_id = $1",
                case_id,
            )
        )
        source = await connection.fetchrow(
            """
            SELECT kind::text AS kind, official_identifier, content_sha256
            FROM source_documents WHERE id = $1
            """,
            source_document_id,
        )
        assert source is not None
        assert str(source["kind"]) == "ATTENDANCE"
        assert str(source["official_identifier"]) == f"AR-PLENARY-XVII-{meeting_bid}"
        assert str(source["content_sha256"]) == content_sha256
        with pytest.raises(asyncpg.PostgresError, match="append-only"):
            await connection.execute(
                "UPDATE parliament_attendance_snapshots "
                "SET meeting_type = 'Alterada' WHERE id = $1",
                snapshot_id,
            )

    assert after_sessions == before_sessions
    assert after_public_attendance == before_public_attendance
    assert publication_events == 0
