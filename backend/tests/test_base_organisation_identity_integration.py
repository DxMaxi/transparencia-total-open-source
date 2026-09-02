"""Prova V5.52 numa base descartável, nunca em dados reais ou produção."""

import asyncio
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.models.base_organisation import (
    BaseOrganisationIdentityEditorialProposalRequest,
    BaseOrganisationIdentityObservationInput,
)
from app.models.editorial import (
    EditorialAction,
    EditorialCaseCreateRequest,
    EditorialCorrectionRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.base_organisation_editorial import BaseOrganisationEditorialRepository
from app.repositories.base_organisation_staging import BaseOrganisationStagingRepository
from app.repositories.editorial import (
    EditorialConflictError,
    EditorialRepository,
    EditorialSourceError,
)
from app.repositories.postgres import PostgresRepository

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="Exige PostgreSQL descartável identificado"
)
PUBLIC_TABLES = (
    "organisations",
    "interest_entities",
    "public_contracts",
    "public_contract_parties",
    "contract_match_reviews",
    "interest_relationships",
    "data_publication_reviews",
    "editorial_publication_events",
)


@pytest.fixture
async def repository():
    repo = PostgresRepository(
        Settings(
            environment="test",
            protected_identifier_pepper=SecretStr("p" * 32),
        )
    )
    await repo.connect()
    try:
        assert repo.pool is not None
        async with repo.pool.acquire() as connection:
            assert str(await connection.fetchval("SELECT current_database()")).endswith("_test")
            assert await connection.fetchval(
                "SELECT to_regclass('auth.tt_disposable_test_marker') IS NOT NULL"
            ), "Recusado: destino não identificado como descartável"
            assert await connection.fetchval(
                "SELECT singleton FROM auth.tt_disposable_test_marker WHERE singleton = TRUE"
            )
        yield repo
    finally:
        await repo.close()


async def _fixture(repo):
    # Referências deliberadamente não fiscais; não dependem do NIPC sintético.
    suffix = uuid.uuid4().hex.translate(str.maketrans("0123456789", "ghijklmnop"))
    source_id = f"source_org_{suffix}"
    record_id = f"ACT-{suffix}"
    now = datetime.now(UTC).replace(microsecond=0)
    url = "https://publicacoes.mj.pt/DetalhePublicacao.aspx"
    content_hash = hashlib.sha256(f"synthetic-identity:{suffix}".encode()).hexdigest()
    auth_user_id = uuid.uuid4()
    actor = StaffSession(
        staff_id=f"staff_org_{suffix}",
        auth_user_id=auth_user_id,
        public_alias=f"revisor-{suffix}",
        role=StaffRole.REVIEWER,
        assurance_level="aal2",
        mfa_required=True,
    )
    async with repo.pool.acquire() as connection, connection.transaction():
        await connection.execute(
            """INSERT INTO source_documents
            (id, publisher, kind, title, official_identifier, url, retrieved_at,
             content_sha256, mime_type)
            VALUES ($1, 'JUSTICE_REGISTRY', 'ORGANISATION_REGISTRY',
                    'Ato fictício para ensaio privado', $2, $3, $4, $5, 'text/html')""",
            source_id,
            record_id,
            url,
            now.replace(tzinfo=None),
            content_hash,
        )
        await connection.execute(
            """INSERT INTO source_archive_attestations
            (id, source_document_id, storage_backend, storage_key, content_sha256,
             byte_size, mime_type, retrieval_url, retrieved_at, archived_at,
             archived_by, attestation_sha256)
            VALUES ($1, $2, 'LOCAL_TEST', $3, $4, 128, 'text/html', $5, $6, $6,
                    'test-v552', $7)""",
            f"archive_org_{suffix}",
            source_id,
            f"sha256/{content_hash[:2]}/{content_hash}",
            content_hash,
            url,
            now.replace(tzinfo=None),
            hashlib.sha256(f"archive:{suffix}".encode()).hexdigest(),
        )
        await connection.execute("INSERT INTO auth.users(id) VALUES ($1)", auth_user_id)
        await connection.execute(
            """INSERT INTO staff_profiles
            (id, auth_user_id, public_alias, role, active, updated_at)
            VALUES ($1, $2, $3, 'REVIEWER', TRUE, NOW())""",
            actor.staff_id,
            auth_user_id,
            actor.public_alias,
        )
    payload = BaseOrganisationIdentityObservationInput(
        source_document_id=source_id,
        registry_record_id=record_id,
        legal_name="Organização Fictícia de Ensaio",
        kind="COMPANY",
        fiscal_identifier=SecretStr("123456789"),
        confirm_independent_official_source=True,
        confirm_identifier_hmac_only=True,
        confirm_private_identity_only=True,
        confirm_no_publication=True,
    )
    return payload, actor


async def _public_counts(repo):
    return {
        table: await repo.pool.fetchval(f'SELECT COUNT(*) FROM "{table}"')
        for table in PUBLIC_TABLES
    }


def _request(candidate):
    return BaseOrganisationIdentityEditorialProposalRequest(
        observation_id=candidate["observation_id"],
        source_record_sha256=candidate["source_record_sha256"],
        proposal_confirmation_sha256=candidate["proposal_confirmation_sha256"],
        confirm_independent_official_source=True,
        confirm_private_identity_only=True,
        confirm_no_publication=True,
    )


async def _stage(repo, payload, actor):
    return await BaseOrganisationStagingRepository(repo.pool, repo.settings).stage_observation(
        payload=payload,
        actor_alias=actor.public_alias,
    )


@pytest.mark.asyncio
async def test_identity_approval_is_private_and_hashes_never_leave_observation(repository, caplog):
    repo = repository
    payload, actor = await _fixture(repo)
    before = await _public_counts(repo)
    staged = await _stage(repo, payload, actor)
    assert staged["created"] is True
    repeated = await _stage(repo, payload, actor)
    assert repeated["created"] is False
    assert repeated["observation_id"] == staged["observation_id"]
    adapter = BaseOrganisationEditorialRepository(repo.pool)
    result = await adapter.list_candidates(query=payload.registry_record_id, limit=20, offset=0)
    candidate = result["items"][0]
    assert result["total"] == 1 and candidate["proposal_eligible"] is True
    request = _request(candidate)
    submissions = await asyncio.gather(
        *(adapter.create_proposal(payload=request, actor=actor) for _ in range(2))
    )
    assert sorted(item["created"] for item in submissions) == [False, True]
    case_id = submissions[0]["case"]["id"]
    assert submissions[1]["case"]["id"] == case_id
    editorial = EditorialRepository(repo.pool)
    await editorial.transition(
        case_id=case_id,
        action=EditorialAction.START_REVIEW,
        expected_revision=1,
        rationale="Início explícito da verificação da prova oficial fictícia.",
        source_confirmed=False,
        actor=actor,
    )
    approved = await editorial.transition(
        case_id=case_id,
        action=EditorialAction.APPROVE,
        expected_revision=2,
        rationale="Prova fictícia revista apenas para identidade organizacional privada.",
        source_confirmed=True,
        actor=actor,
    )
    assert approved["current_state"] == "APPROVED"
    assert approved["origin"] == "INGESTION"
    assert approved["publication_events"] == []
    assert await _public_counts(repo) == before
    private = await repo.pool.fetchrow(
        "SELECT protected_identifier_digest, observation_sha256 "
        "FROM base_organisation_identity_observations WHERE id=$1",
        staged["observation_id"],
    )
    audit = await repo.pool.fetch(
        "SELECT to_jsonb(a)::text AS item FROM audit_events a WHERE entity_id IN ($1, $2)",
        staged["observation_id"],
        case_id,
    )
    serialised = json.dumps(
        [staged, repeated, result, submissions, approved, [r["item"] for r in audit]], default=str
    )
    for sensitive in (
        "123456789",
        private["protected_identifier_digest"],
        private["observation_sha256"],
    ):
        assert sensitive not in serialised
        assert sensitive not in caplog.text
    # Another official source can describe the same protected identifier without exposing a key.
    other_payload, other_actor = await _fixture(repo)
    other = await _stage(repo, other_payload, other_actor)
    other_private = await repo.pool.fetchrow(
        "SELECT protected_identifier_digest, observation_sha256 "
        "FROM base_organisation_identity_observations WHERE id=$1",
        other["observation_id"],
    )
    assert other_private["protected_identifier_digest"] == private["protected_identifier_digest"]
    assert other["source_record_sha256"] != staged["source_record_sha256"]
    assert other["observation_id"] != staged["observation_id"]
    assert other_private["observation_sha256"] != private["observation_sha256"]
    with pytest.raises(EditorialConflictError, match="nova observação"):
        await editorial.correct_case(
            case_id=case_id,
            payload=EditorialCorrectionRequest(
                expected_revision=3,
                rationale="Tentativa de alterar manualmente a identidade.",
                normalized_data={"identity_hmac": "a" * 64},
            ),
            actor=actor,
        )
    with pytest.raises(ValidationError, match="proposta privada específica"):
        EditorialCaseCreateRequest(
            kind="ORGANISATION_IDENTITY",
            subject_type="ORGANISATION",
            subject_id="fake",
            source_document_id=payload.source_document_id,
            normalized_data={"identity_hmac": "a" * 64},
            confirm_private_only=True,
        )
    unchanged = await editorial.get_case(case_id)
    assert len(unchanged["versions"]) == 1 and len(unchanged["decisions"]) == 3
    assert await _public_counts(repo) == before


@pytest.mark.asyncio
async def test_stale_confirmation_late_failure_and_fiscal_rationale_rollback(
    repository, monkeypatch
):
    repo = repository
    payload, actor = await _fixture(repo)
    staged = await _stage(repo, payload, actor)
    adapter = BaseOrganisationEditorialRepository(repo.pool)
    candidate = (
        await adapter.list_candidates(query=payload.registry_record_id, limit=20, offset=0)
    )["items"][0]
    request = _request(candidate)
    before_cases = await repo.pool.fetchval("SELECT COUNT(*) FROM editorial_cases")
    before_audit = await repo.pool.fetchval("SELECT COUNT(*) FROM audit_events")
    with pytest.raises(EditorialConflictError):
        await adapter.create_proposal(
            payload=request.model_copy(update={"proposal_confirmation_sha256": "f" * 64}),
            actor=actor,
        )
    original = adapter.get_exact_candidate
    calls = 0

    async def late_failure(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            return None
        return await original(**kwargs)

    monkeypatch.setattr(adapter, "get_exact_candidate", late_failure)
    with pytest.raises(EditorialConflictError, match="durante"):
        await adapter.create_proposal(payload=request, actor=actor)
    assert await repo.pool.fetchval("SELECT COUNT(*) FROM editorial_cases") == before_cases
    assert await repo.pool.fetchval("SELECT COUNT(*) FROM audit_events") == before_audit
    monkeypatch.setattr(adapter, "get_exact_candidate", original)
    created = await adapter.create_proposal(payload=request, actor=actor)
    case_id = created["case"]["id"]
    with pytest.raises(EditorialConflictError, match="identificadores protegidos"):
        await EditorialRepository(repo.pool).transition(
            case_id=case_id,
            action=EditorialAction.START_REVIEW,
            expected_revision=1,
            rationale="Identificador que não deve ser gravado: 123 456 789",
            source_confirmed=False,
            actor=actor,
        )
    assert (await EditorialRepository(repo.pool).get_case(case_id))["revision"] == 1
    assert staged["publication_performed"] is False


@pytest.mark.asyncio
async def test_registry_sources_cannot_bypass_dedicated_identity_review(repository):
    repo = repository
    payload, actor = await _fixture(repo)
    editorial = EditorialRepository(repo.pool)
    assert await editorial.list_source_candidates(query=payload.registry_record_id, limit=20) == []
    with pytest.raises(EditorialSourceError, match="circuito privado"):
        await editorial.create_case(
            payload=EditorialCaseCreateRequest(
                kind="OTHER",
                subject_type="OTHER",
                subject_id="bypass",
                source_document_id=payload.source_document_id,
                normalized_data={"safe": "test"},
                confirm_private_only=True,
            ),
            actor=actor,
        )
    staged = await _stage(repo, payload, actor)
    async with repo.pool.acquire() as connection:
        for origin, subject_type, subject_id in (
            ("HUMAN", "BASE_ORGANISATION_IDENTITY_OBSERVATION", staged["observation_id"]),
            ("AI", "BASE_ORGANISATION_IDENTITY_OBSERVATION", staged["observation_id"]),
            ("INGESTION", "OTHER", staged["observation_id"]),
            ("INGESTION", "BASE_ORGANISATION_IDENTITY_OBSERVATION", "missing"),
        ):
            with pytest.raises(asyncpg.PostgresError, match="observação privada exata"):
                async with connection.transaction():
                    await connection.execute(
                        """INSERT INTO editorial_cases
                        (id,kind,subject_type,subject_id,source_document_id,origin,
                         created_by_alias,updated_at)
                        VALUES ($1,'ORGANISATION_IDENTITY',$2,$3,$4,$5,'test',NOW())""",
                        f"case_{uuid.uuid4().hex}",
                        subject_type,
                        subject_id,
                        payload.source_document_id,
                        origin,
                    )


@pytest.mark.asyncio
async def test_database_privacy_immutability_and_legacy_guards(repository):
    repo = repository
    payload, actor = await _fixture(repo)
    staged = await _stage(repo, payload, actor)
    adapter = BaseOrganisationEditorialRepository(repo.pool)
    candidate = (
        await adapter.list_candidates(query=payload.registry_record_id, limit=20, offset=0)
    )["items"][0]
    created = await adapter.create_proposal(payload=_request(candidate), actor=actor)
    async with repo.pool.acquire() as connection:
        for sql, args in (
            (
                "UPDATE base_organisation_identity_observations "
                "SET legal_name='Alterada' WHERE id=$1",
                [staged["observation_id"]],
            ),
            (
                "DELETE FROM base_organisation_identity_observations WHERE id=$1",
                [staged["observation_id"]],
            ),
            ("TRUNCATE base_organisation_identity_observations", []),
            (
                "UPDATE source_documents SET title='Alterada' WHERE id=$1",
                [payload.source_document_id],
            ),
            (
                "UPDATE source_documents SET publisher='BASE_GOV' WHERE id=$1",
                [payload.source_document_id],
            ),
            (
                "UPDATE editorial_cases SET current_state='PUBLISHED' WHERE id=$1",
                [created["case"]["id"]],
            ),
        ):
            with pytest.raises(asyncpg.PostgresError):
                async with connection.transaction():
                    await connection.execute(sql, *args)
        with pytest.raises(asyncpg.PostgresError, match="ORGANISATION_IDENTITY"):
            async with connection.transaction():
                await connection.execute(
                    """INSERT INTO editorial_publication_events
                    (id, case_id, version_id, action, target_type, target_id,
                     rationale, actor_id, actor_alias, event_sha256)
                    VALUES ($1,$2,$3,'PUBLISH','ORGANISATION','none',
                            'Tentativa proibida de publicação', $4,$5,$6)""",
                    f"event_{uuid.uuid4().hex}",
                    created["case"]["id"],
                    created["case"]["current_version_id"],
                    actor.staff_id,
                    actor.public_alias,
                    "a" * 64,
                )
        with pytest.raises(asyncpg.PostgresError, match="NORMALISED_NAME"):
            async with connection.transaction():
                await connection.execute(
                    """INSERT INTO contract_match_reviews
                    (id,public_contract_id,interest_entity_id,method,candidate_label,
                     rationale,evidence_document_id)
                    VALUES ('forbidden-name','none','none','NORMALISED_NAME',
                            'Nome coincidente','Não é prova',$1)""",
                    payload.source_document_id,
                )
        assert await connection.fetchval(
            "SELECT relrowsecurity FROM pg_class "
            "WHERE oid='base_organisation_identity_observations'::regclass"
        )
        for role in ("anon", "authenticated"):
            for function in (
                "validate_editorial_case_insert()",
                "base_organisation_identity_safe_text(text)",
                "validate_base_organisation_identity_observation_insert()",
                "protect_base_organisation_identity_source()",
                "reject_base_organisation_identity_observation_mutation()",
                "reject_new_normalised_name_contract_match()",
                "enforce_organisation_identity_case_private()",
                "reject_organisation_identity_publication_event()",
            ):
                assert not await connection.fetchval(
                    "SELECT has_function_privilege($1,$2,'EXECUTE')",
                    role,
                    function,
                )
            for privilege in (
                "SELECT",
                "INSERT",
                "UPDATE",
                "DELETE",
                "TRUNCATE",
                "REFERENCES",
                "TRIGGER",
            ):
                assert not await connection.fetchval(
                    "SELECT has_table_privilege($1,'base_organisation_identity_observations',$2)",
                    role,
                    privilege,
                )
            async with connection.transaction():
                await connection.execute(f"SET LOCAL ROLE {role}")
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    async with connection.transaction():
                        await connection.fetch(
                            "SELECT * FROM public.base_organisation_identity_observations"
                        )
        for unsafe in (
            "123456789",
            "abc123 456 789xyz",
            "１２３４５６７８９",
            "١٢٣٤٥٦٧٨٩",
            "१२३४५६७८९",
            "a" * 64,
            "aa-" * 32,
        ):
            assert not await connection.fetchval(
                "SELECT base_organisation_identity_safe_text($1)", unsafe
            )
        assert await connection.fetchval(
            "SELECT base_organisation_identity_safe_text('ACT-1-2026')"
        )


@pytest.mark.asyncio
async def test_migration_preflight_preserves_legacy_fiscal_values(repository):
    sql = (
        Path(__file__).resolve().parents[2]
        / "prisma/migrations/20260902090000_v5_base_organisation_identity_editorial/migration.sql"
    ).read_text(encoding="utf-8")
    preflight = sql[sql.index("DO $$") : sql.index("$$;", sql.index("DO $$")) + 3]
    async with repository.pool.acquire() as connection:
        tx = connection.transaction()
        await tx.start()
        try:
            # A transient schema masks only the legacy table; rollback discards the fixture.
            schema = f"v552_preflight_{uuid.uuid4().hex}"
            await connection.execute(f'CREATE SCHEMA "{schema}"')
            await connection.execute(f'SET LOCAL search_path TO "{schema}", public')
            await connection.execute("CREATE TABLE organisations (id TEXT, public_nipc TEXT)")
            await connection.execute("INSERT INTO organisations VALUES ('synthetic','123456789')")
            with pytest.raises(asyncpg.PostgresError, match="valores legados"):
                async with connection.transaction():
                    await connection.execute(preflight)
            assert await connection.fetchval("SELECT public_nipc FROM organisations") == "123456789"
            await connection.execute("UPDATE organisations SET public_nipc=NULL")
            await connection.execute(preflight)
            assert await connection.fetchval("SELECT COUNT(*) FROM organisations") == 1
            assert not await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
                "WHERE table_schema=$1 AND table_name='organisations' "
                "AND column_name='public_nipc')",
                schema,
            )
        finally:
            await tx.rollback()
