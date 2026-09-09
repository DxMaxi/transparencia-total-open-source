"""V5.54: correspondência exata exercitada em PostgreSQL descartável."""

# ruff: noqa: F811
import asyncio
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime

import asyncpg
import pytest
from test_base_contract_editorial_integration import (
    _ensure_catalogue_scope,
    _prepare_disposable_auth_user,
)
from test_base_organisation_identity_integration import repository  # noqa: F401
from test_base_organisation_publication import _approve, _prepare, _publication, _withdrawal

from app.models.base_contract_organisation_match import (
    BaseContractOrganisationMatchCandidateRequest,
)
from app.models.editorial import (
    BaseContractEditorialProposalRequest,
    BaseContractPublicationRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.base_contract_editorial import BaseContractEditorialRepository
from app.repositories.base_contract_organisation_match import (
    BaseContractOrganisationMatchRepository,
)
from app.repositories.base_contract_publication import BaseContractPublicationRepository
from app.repositories.editorial import (
    EditorialConflictError,
    EditorialNotFoundError,
    EditorialSourceError,
)

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="PostgreSQL descartável")


async def _contract(repository, protected_digest):
    scope_id = await _ensure_catalogue_scope()
    suffix = uuid.uuid4().hex[:12].translate(str.maketrans("0123456789", "ghijklmnop"))
    source_sha256 = hashlib.sha256(f"base-contract:{suffix}".encode()).hexdigest()
    resource_url = (
        "https://dados.gov.pt/s/resources/contratos-publicos-portal-base-impic-"
        "contratos-de-2012-a-2026/20260823/contratos2025.zip"
    )
    collected_at = datetime(2026, 8, 29, 11, 0, tzinfo=UTC).replace(tzinfo=None)
    auth_user_id = uuid.uuid4()
    staff_id = f"staff_base_{suffix}"
    alias = f"revisor-base-{suffix}"
    source_document_id = f"source_base_{suffix}"
    batch_id = f"batch_base_{suffix}"
    contract_snapshot_id = f"contract_base_{suffix}"
    official_contract_id = f"BASE-{suffix}"

    async with repository.pool.acquire() as connection, connection.transaction():
        assert await connection.fetchval(
            "SELECT EXISTS (SELECT 1 FROM base_contract_catalogue_resources "
            "WHERE scope_id = $1 AND resource_year = 2025)",
            scope_id,
        )
        await connection.execute(
            """
            INSERT INTO source_documents
                (id, publisher, kind, title, url, retrieved_at, content_sha256,
                 mime_type, parser_version, created_at)
            VALUES ($1, 'BASE_GOV', 'OPEN_DATASET', 'Portal BASE — contratos — 2025',
                    $2, $3, $4, 'application/zip', 'base-contracts-test-v1', NOW())
            """,
            source_document_id,
            resource_url,
            collected_at,
            source_sha256,
        )
        await connection.execute(
            """
            INSERT INTO source_archive_attestations
                (id, source_document_id, storage_backend, storage_key,
                 content_sha256, byte_size, mime_type, retrieval_url,
                 retrieved_at, archived_at, archived_by,
                 attestation_sha256, created_at)
            VALUES ($1, $2, 'POSTGRES', $3, $4, 1002025, 'application/zip',
                    $5, $6, $6, 'test:v5.50', $7, NOW())
            """,
            f"archive_base_{suffix}",
            source_document_id,
            f"sha256/{source_sha256[:2]}/{source_sha256}",
            source_sha256,
            resource_url,
            collected_at,
            hashlib.sha256(f"attestation:{suffix}".encode()).hexdigest(),
        )
        await connection.execute(
            """
            INSERT INTO sync_runs
                (id, source_name, dataset_url, status, started_at, finished_at,
                 records_read, records_written, warnings, code_version)
            VALUES ($1, 'BASE_GOV', $2, 'SUCCEEDED', $3, $3, 1, 2, '[]'::jsonb,
                    'base-contracts-test-v1')
            """,
            f"run_base_{suffix}",
            resource_url,
            collected_at,
        )
        await connection.execute(
            """
            INSERT INTO base_staging_batches
                (id, source_document_id, sync_run_id, resource_year, resource_title,
                 resource_format, parser_version, normalised_sha256,
                 identifier_digests_stored, contract_count, party_count,
                 collected_at, created_at)
            VALUES ($1, $2, $3, 2025, 'contratos2025.zip', 'ZIP',
                    'base-contracts-test-v1', $4, TRUE, 1, 1, $5, NOW())
            """,
            batch_id,
            source_document_id,
            f"run_base_{suffix}",
            hashlib.sha256(f"batch:{suffix}".encode()).hexdigest(),
            collected_at,
        )
        await connection.execute(
            """
            INSERT INTO base_contract_snapshots
                (id, batch_id, source_id, object, procedure, cpv_code, contract_value,
                 currency, published_at, direct_official_url, created_at)
            VALUES ($1, $2, $3, 'Aquisição pública para teste editorial',
                    'PUBLIC_TENDER', '45000000-7', 123456789.00, 'EUR', $4,
                    'https://www.base.gov.pt/Base4/pt/detalhe/?type=contratos&id=1', NOW())
            """,
            contract_snapshot_id,
            batch_id,
            official_contract_id,
            collected_at,
        )
        await connection.execute(
            """
            INSERT INTO base_contract_party_snapshots
                (id, contract_snapshot_id, ordinal, role, source_name,
                 protected_identifier_digest, created_at)
            VALUES ($1, $2, 0, 'CONTRACTOR', 'Fornecedor Oficial de Teste, Lda.', $3, NOW())
            """,
            f"party_base_{suffix}",
            contract_snapshot_id,
            protected_digest,
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
    editorial = BaseContractEditorialRepository(repository.pool)
    candidate = (
        await editorial.list_candidates(
            query=official_contract_id, resource_year=2025, limit=20, cursor=None
        )
    )["items"][0]
    request = BaseContractEditorialProposalRequest(
        contract_snapshot_id=contract_snapshot_id,
        source_record_sha256=candidate["source_record_sha256"],
        confirm_private_only=True,
        confirm_normalized_batch_consistency=True,
        confirm_exact_official_contract_id=True,
        confirm_no_party_identity_or_name_matching=True,
        confirm_organisations_require_independent_sources=True,
        confirm_no_contract_or_relationship_publication=True,
    )
    case_id = (await editorial.create_proposal(payload=request, actor=actor))["case"]["id"]
    await _approve(repository, case_id, actor)
    publication = BaseContractPublicationRepository(repository.pool)
    preview = await publication.inspect_publication(case_id=case_id)
    request = BaseContractPublicationRequest(
        **{
            f"expected_{field}": preview[field]
            for field in (
                "revision",
                "case_id",
                "version_id",
                "version_sha256",
                "contract_snapshot_id",
                "public_contract_id",
                "official_contract_id_sha256",
                "source_record_sha256",
                "publication_proof_sha256",
            )
        },
        expected_source_sha256=source_sha256,
        rationale="Fonte sintética revista para ensaio da correspondência privada.",
        public_rationale="Contrato sintético revisto e publicado para ensaio isolado.",
        confirm_source_reviewed=True,
        confirm_exact_official_contract_id=True,
        confirm_no_party_publication=True,
        confirm_no_identity_or_name_matching=True,
        confirm_no_organisation_match_or_relationship_creation=True,
        confirm_append_only_publication=True,
        confirm_publication=True,
    )
    result = await publication.publish(case_id=case_id, payload=request, actor=actor)
    return result["public_contract_id"]


async def _pair(repo):
    organisation, _, case_id, actor, fiscal, staged = await _prepare(repo)
    preview = await organisation.inspect_publication(case_id=case_id)
    result = await organisation.publish(case_id=case_id, payload=_publication(preview), actor=actor)
    digest = await repo.pool.fetchval(
        "SELECT protected_identifier_digest FROM base_organisation_identity_observations "
        "WHERE id=$1",
        staged["observation_id"],
    )
    contract_id = await _contract(repo, digest)
    matcher = BaseContractOrganisationMatchRepository(repo.pool)
    inspection = await matcher.inspect(public_contract_id=contract_id)
    assert inspection["candidate_pair_count"] == 1
    candidate = inspection["items"][0]
    assert candidate["organisation_id"] == result["public_id"]
    request = BaseContractOrganisationMatchCandidateRequest(
        expected_public_contract_id=contract_id,
        **{
            f"expected_{field}": candidate[field]
            for field in (
                "contract_publication_snapshot_id",
                "contract_party_snapshot_id",
                "organisation_id",
                "organisation_publication_snapshot_id",
                "candidate_proof_sha256",
            )
        },
        rationale="Duas fontes oficiais sintéticas confirmadas; proposta privada por rever.",
        **{
            field: True
            for field in BaseContractOrganisationMatchCandidateRequest.model_fields
            if field.startswith("confirm_")
        },
    )
    return matcher, request, actor, organisation, case_id, digest, fiscal, inspection


async def _counts(repo):
    return {
        table: await repo.pool.fetchval(f'SELECT COUNT(*) FROM "{table}"')
        for table in (
            "public_contracts",
            "organisations",
            "public_contract_parties",
            "contract_match_reviews",
            "interest_entities",
            "interest_relationships",
            "editorial_cases",
            "editorial_versions",
            "editorial_decisions",
            "editorial_publication_events",
            "data_publication_reviews",
            "audit_events",
        )
    }


async def test_exact_candidate_is_private_idempotent_concurrent_and_immutable(repository):
    repo = repository
    matcher, request, actor, _, _, digest, fiscal, inspection = await _pair(repo)
    before = await _counts(repo)
    results = await asyncio.gather(
        *(matcher.create(payload=request, actor=actor) for _ in range(3))
    )
    assert sum(result["created"] for result in results) == 1
    assert len({result["id"] for result in results}) == 1
    assert await _counts(repo) == before
    refreshed = await matcher.inspect(public_contract_id=request.expected_public_contract_id)
    assert refreshed["items"][0]["eligible"] is False
    assert refreshed["items"][0]["existing_candidate"]["id"] == results[0]["id"]
    serialized = json.dumps([inspection, refreshed, results], default=str)
    assert digest not in serialized and fiscal not in serialized
    assert "organisation_identity_observation_id" not in serialized
    candidate_id = results[0]["id"]
    persisted = await repo.pool.fetchval(
        "SELECT row_to_json(c)::text FROM base_contract_organisation_match_candidates c "
        "WHERE id=$1",
        candidate_id,
    )
    assert digest not in persisted and fiscal not in persisted
    with pytest.raises(asyncpg.PostgresError, match="prova canónica"):
        await repo.pool.execute(
            """INSERT INTO base_contract_organisation_match_candidates
               SELECT (jsonb_populate_record(
                 NULL::base_contract_organisation_match_candidates,
                 to_jsonb(c) || jsonb_build_object(
                   'id', $2::text, 'candidate_proof_sha256', repeat('0',64))
               )).* FROM base_contract_organisation_match_candidates c WHERE id=$1""",
            candidate_id,
            "base_contract_org_candidate_" + uuid.uuid4().hex,
        )
    for sql in (
        "UPDATE base_contract_organisation_match_candidates SET decision='CONFIRMED' WHERE id=$1",
        "DELETE FROM base_contract_organisation_match_candidates WHERE id=$1",
    ):
        with pytest.raises(asyncpg.PostgresError, match="append-only"):
            await repo.pool.execute(sql, candidate_id)
    for table in (
        "base_contract_organisation_match_candidates",
        "source_archive_attestations",
        "public_contract_parties",
        "contract_match_reviews",
        "interest_relationships",
    ):
        with pytest.raises(asyncpg.PostgresError):
            await repo.pool.execute(f'TRUNCATE "{table}" CASCADE')
    for role in ("anon", "authenticated"):
        async with repo.pool.acquire() as connection, connection.transaction():
            await connection.execute(f'SET LOCAL ROLE "{role}"')
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                async with connection.transaction():
                    await connection.fetch(
                        "SELECT * FROM public.base_contract_organisation_match_candidates"
                    )
    assert (
        await repo.pool.fetchval(
            "SELECT relrowsecurity FROM pg_class WHERE "
            "oid='base_contract_organisation_match_candidates'::regclass"
        )
        is True
    )


async def test_stale_proof_inactive_actor_withdrawal_and_different_identifier_are_rejected(
    repository,
):
    repo = repository
    matcher, request, actor, organisation, case_id, _, _, _ = await _pair(repo)
    before = await _counts(repo)
    with pytest.raises(EditorialConflictError, match="prova"):
        await matcher.create(
            payload=request.model_copy(update={"expected_candidate_proof_sha256": "0" * 64}),
            actor=actor,
        )
    with pytest.raises(EditorialConflictError, match="multifator"):
        await matcher.create(
            payload=request, actor=actor.model_copy(update={"assurance_level": "aal1"})
        )
    await repo.pool.execute("UPDATE staff_profiles SET active=FALSE WHERE id=$1", actor.staff_id)
    with pytest.raises(EditorialConflictError):
        await matcher.create(payload=request, actor=actor)
    await repo.pool.execute("UPDATE staff_profiles SET active=TRUE WHERE id=$1", actor.staff_id)
    assert await _counts(repo) == before
    # O nome da parte é o mesmo; a identidade distinta tem de produzir zero candidatos.
    unrelated = await _contract(repo, hashlib.sha256(uuid.uuid4().bytes).hexdigest())
    assert (await matcher.inspect(public_contract_id=unrelated))["items"] == []
    await matcher.create(payload=request, actor=actor)
    withdrawal = await organisation.inspect_withdrawal(case_id=case_id)
    await organisation.withdraw(case_id=case_id, payload=_withdrawal(withdrawal), actor=actor)
    assert (await matcher.inspect(public_contract_id=request.expected_public_contract_id))[
        "items"
    ] == []
    with pytest.raises((EditorialSourceError, EditorialNotFoundError)):
        await matcher.create(payload=request, actor=actor)
    assert (
        await repo.pool.fetchval(
            "SELECT COUNT(*) FROM base_contract_organisation_match_candidates "
            "WHERE public_contract_id=$1",
            request.expected_public_contract_id,
        )
        == 1
    )
