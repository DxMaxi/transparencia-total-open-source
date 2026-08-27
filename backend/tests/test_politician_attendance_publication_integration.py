import hashlib
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import asyncpg
import pytest

from app.core.config import Settings
from app.models.archive import PrivateRawDocument
from app.models.editorial import (
    EditorialAction,
    PoliticianAttendanceEditorialProposalRequest,
    PoliticianAttendancePublicationRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.editorial import EditorialConflictError, EditorialRepository
from app.repositories.parliament_attendance import ParliamentAttendanceRepository
from app.repositories.politician_attendance_editorial import (
    PoliticianAttendanceEditorialRepository,
)
from app.repositories.politician_attendance_publication import (
    PoliticianAttendancePublicationRepository,
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


def _html(*, deputy_seed: int, marker: str) -> bytes:
    rows: list[str] = []
    for index in range(100):
        status = "Falta Justificada (FJ)" if index == 0 else "Presença (P)"
        reason = "<td>Motivo Missão parlamentar</td>" if index == 0 else "<td></td>"
        rows.append(
            "<tr><td>Deputado "
            f'<a href="/DeputadoGP/Paginas/Biografia.aspx?BID={deputy_seed + index}">'
            f"Pessoa Publicação {marker} {index:03d}</a></td>"
            "<td>Grupo Parlamentar/Partido TESTE</td>"
            f"<td>Presença/Falta {status}</td>{reason}</tr>"
        )
    return (
        "<html><body><h1>Reunião Plenária Ordinária de 2026-07-17.</h1><table>"
        + "".join(rows)
        + "</table>"
        '<a href="https://app.parlamento.pt/webutils/docs/doc.pdf?'
        f'Fich=XVII_1_111_{marker}_2026-07-17.pdf&amp;Inline=true">PDF</a>'
        "</body></html>"
    ).encode()


@pytest.fixture
async def repository() -> AsyncIterator[ParliamentAttendanceRepository]:
    repo = ParliamentAttendanceRepository(Settings(environment="test"))
    await repo.connect()
    try:
        yield repo
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_admin_publishes_whole_attendance_meeting_or_nothing(
    repository: ParliamentAttendanceRepository,
) -> None:
    assert repository.pool is not None
    suffix = uuid.uuid4().hex[:12]
    meeting_bid = str(700_000_000_000 + int(suffix, 16) % 200_000_000_000)
    deputy_seed = 20_000_000_000 + int(suffix, 16) % 1_000_000_000
    source_url = (
        "https://www.parlamento.pt/DeputadoGP/Paginas/"
        f"DetalheReuniaoPlenaria.aspx?BID={meeting_bid}"
    )
    content = _html(deputy_seed=deputy_seed, marker=suffix)
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
    stored = await ParliamentAttendanceStager(
        Settings(environment="test"),
        repository,
    ).store(dataset)
    snapshot_id = str(stored["normalised_snapshot_id"])
    source_document_id = str(stored["source_document_id"])

    staff_id = f"staff_attendance_publication_{suffix}"
    auth_user_id = uuid.uuid4()
    alias = f"admin-attendance-{suffix}"
    person_rows: list[tuple[object, ...]] = []
    mandate_rows: list[tuple[object, ...]] = []
    review_rows: list[tuple[object, ...]] = []
    for index in range(100):
        person_id = f"person_attendance_{suffix}_{index}"
        mandate_id = f"mandate_attendance_{suffix}_{index}"
        official_deputy_id = str(deputy_seed + index)
        person_rows.append(
            (
                person_id,
                official_deputy_id,
                f"Pessoa Publicação {suffix} {index:03d}",
                f"Pessoa Publicação {index:03d}",
                f"pessoa-attendance-{suffix}-{index}",
            )
        )
        mandate_rows.append(
            (
                mandate_id,
                person_id,
                "XVII",
                f"Círculo teste {suffix}",
                source_document_id,
            )
        )
        review_rows.extend(
            [
                (
                    f"person_review_attendance_{suffix}_{index}",
                    "PERSON",
                    person_id,
                    source_document_id,
                    alias,
                ),
                (
                    f"mandate_review_attendance_{suffix}_{index}",
                    "MANDATE",
                    mandate_id,
                    source_document_id,
                    alias,
                ),
            ]
        )

    async with repository.pool.acquire() as connection, connection.transaction():
        await connection.executemany(
            """
            INSERT INTO people
                (id, source_id, full_name, parliamentary_name, slug, role,
                 photo_url, official_profile_url, active, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, 'DEPUTY', NULL, NULL, TRUE, NOW(), NOW())
            """,
            person_rows,
        )
        await connection.executemany(
            """
            INSERT INTO mandates
                (id, person_id, party_id, legislature, office_title,
                 constituency, started_at, ended_at, source_document_id,
                 source_observation_id, source_period_ordinal,
                 source_period_sha256, created_at, updated_at)
            VALUES ($1, $2, NULL, $3, 'Deputado à Assembleia da República',
                    $4, '2026-01-01'::timestamp, NULL, $5,
                    NULL, NULL, NULL, NOW(), NOW())
            """,
            mandate_rows,
        )
        await connection.executemany(
            """
            INSERT INTO data_publication_reviews
                (id, entity_type, entity_id, purpose, legal_basis, sensitivity,
                 necessity_assessment, proportionality_test, retention_until,
                 publishable, source_document_id, reviewed_by, reviewed_at)
            VALUES ($1, $2, $3, 'Teste descartável de publicação integral',
                    'PUBLIC_INTEREST', 'PUBLIC_PERSONAL',
                    'Identificador oficial exato necessário para o teste.',
                    'Sem correspondência por nome ou criação de novas identidades.',
                    NULL, TRUE, $4, $5, NOW())
            """,
            review_rows,
        )
        await _prepare_disposable_auth_user(connection, auth_user_id)
        await connection.execute(
            """
            INSERT INTO staff_profiles
                (id, auth_user_id, public_alias, role, active, created_at, updated_at)
            VALUES ($1, $2, $3, 'ADMIN', TRUE, NOW(), NOW())
            """,
            staff_id,
            auth_user_id,
            alias,
        )

    actor = StaffSession(
        staff_id=staff_id,
        auth_user_id=auth_user_id,
        public_alias=alias,
        role=StaffRole.ADMIN,
        assurance_level="aal2",
        mfa_required=False,
    )
    candidates = PoliticianAttendanceEditorialRepository(repository.pool)
    catalogue = await candidates.list_candidates(legislature="XVII", limit=20, offset=0)
    candidate = next(item for item in catalogue["items"] if item["snapshot_id"] == snapshot_id)
    assert candidate["publication_ready"] is True
    assert candidate["identity_reconciliation"]["reviewed_identities"] == 100
    assert candidate["identity_reconciliation"]["reviewed_covering_mandates"] == 100

    proposal = await candidates.create_proposal(
        payload=PoliticianAttendanceEditorialProposalRequest(
            snapshot_id=snapshot_id,
            confirm_private_only=True,
            confirm_complete_meeting=True,
            confirm_exact_official_ids_only=True,
            confirm_no_name_matching=True,
            confirm_absence_is_not_noncompliance=True,
            confirm_no_selective_processing=True,
        ),
        actor=actor,
    )
    proposal_case = proposal["case"]
    assert isinstance(proposal_case, dict)
    case_id = str(proposal_case["id"])
    editorial = EditorialRepository(repository.pool)
    await editorial.transition(
        case_id=case_id,
        action=EditorialAction.START_REVIEW,
        expected_revision=1,
        rationale="A reunião integral será comparada novamente com a fonte arquivada.",
        source_confirmed=False,
        actor=actor,
    )
    approved = await editorial.transition(
        case_id=case_id,
        action=EditorialAction.APPROVE,
        expected_revision=2,
        rationale="Todos os BID, estados e mandatos foram revistos na fonte oficial.",
        source_confirmed=True,
        actor=actor,
    )

    publisher = PoliticianAttendancePublicationRepository(repository.pool)
    preview = await publisher.inspect(case_id=case_id)
    assert preview["eligible"] is True
    assert preview["mapping_sha256"] is not None
    assert preview["publication_proof_sha256"] is not None
    public_effect = preview["public_effect"]
    assert isinstance(public_effect, dict)
    assert public_effect["attendance_records_to_create"] == 100
    assert public_effect["people_to_create"] == 0
    assert public_effect["mandates_to_create"] == 0
    payload = PoliticianAttendancePublicationRequest(
        expected_case_id=case_id,
        expected_version_id=str(approved["current_version_id"]),
        expected_version_sha256=str(preview["version_sha256"]),
        expected_source_sha256=content_sha256,
        expected_snapshot_sha256=str(preview["snapshot_sha256"]),
        expected_mapping_sha256=str(preview["mapping_sha256"]),
        expected_publication_proof_sha256=str(preview["publication_proof_sha256"]),
        expected_record_count=100,
        rationale="A fonte, todos os BID, estados e mandatos foram novamente confirmados.",
        public_rationale="Reunião integral publicada após revisão humana da fonte parlamentar.",
        confirm_source_reviewed=True,
        confirm_complete_meeting=True,
        confirm_exact_official_ids_and_mandates_only=True,
        confirm_all_statuses_reviewed=True,
        confirm_absence_is_not_noncompliance=True,
        confirm_append_only_publication=True,
        confirm_publication=True,
    )

    with pytest.raises(EditorialConflictError):
        await publisher.publish(
            case_id=case_id,
            payload=payload.model_copy(update={"expected_mapping_sha256": "0" * 64}),
            actor=actor,
        )
    async with repository.pool.acquire() as connection:
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM parliamentary_sessions WHERE attendance_snapshot_id = $1",
                snapshot_id,
            )
            == 0
        )

    published = await publisher.publish(case_id=case_id, payload=payload, actor=actor)
    assert published["state"] == "PUBLISHED"
    assert published["attendance_record_count"] == 100
    assert published["people_created"] == 0
    assert published["mandates_created"] == 0
    assert published["absence_is_noncompliance"] is False
    with pytest.raises(EditorialConflictError):
        await publisher.publish(case_id=case_id, payload=payload, actor=actor)

    async with repository.pool.acquire() as connection:
        counts = await connection.fetchrow(
            """
            SELECT COUNT(*)::int AS records,
                   COUNT(*) FILTER (WHERE present = TRUE)::int AS present,
                   COUNT(*) FILTER (WHERE present = FALSE AND is_excused = TRUE)::int
                       AS justified,
                   COUNT(*) FILTER (WHERE present = FALSE AND is_excused = FALSE)::int
                       AS unjustified
            FROM attendance_records
            WHERE session_id = $1
            """,
            str(published["session_id"]),
        )
        assert counts is not None
        assert dict(counts) == {
            "records": 100,
            "present": 99,
            "justified": 1,
            "unjustified": 0,
        }
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM data_publication_reviews "
                "WHERE entity_type = 'PARLIAMENT_ATTENDANCE_SNAPSHOT' "
                "AND entity_id = $1 AND publishable = TRUE",
                snapshot_id,
            )
            == 1
        )
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM editorial_publication_events "
                "WHERE case_id = $1 AND target_type = 'PARLIAMENT_ATTENDANCE_SNAPSHOT'",
                case_id,
            )
            == 1
        )
        first_record_id = await connection.fetchval(
            "SELECT id FROM attendance_records WHERE session_id = $1 ORDER BY id LIMIT 1",
            str(published["session_id"]),
        )
        with pytest.raises(asyncpg.PostgresError, match="append-only"):
            await connection.execute(
                "UPDATE attendance_records SET absence_reason = 'alterada' WHERE id = $1",
                first_record_id,
            )
