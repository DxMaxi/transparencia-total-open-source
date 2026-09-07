"""V5.53: dados sintéticos numa base PostgreSQL explicitamente descartável."""

# ruff: noqa: F811 - a fixture importada é deliberadamente injetada pelo pytest.

import asyncio
import json
import os
import uuid

import asyncpg
import pytest
from pydantic import SecretStr, ValidationError
from test_base_organisation_identity_integration import (
    _fixture,
    _request,
    _stage,
    repository,  # noqa: F401 - fixture partilhada, com verificação do marcador descartável
)

from app.models.api import RightOfReplyRequest
from app.models.base_organisation import (
    OrganisationPublicationProposalRequest,
    OrganisationPublicationRequest,
    OrganisationWithdrawalRequest,
)
from app.models.editorial import EditorialAction, StaffRole
from app.repositories.base_organisation_editorial import BaseOrganisationEditorialRepository
from app.repositories.base_organisation_publication import BaseOrganisationPublicationRepository
from app.repositories.editorial import EditorialConflictError, EditorialRepository
from app.repositories.public_organisations import PublicOrganisationRepository
from app.services.right_of_reply import build_right_of_reply_receipt

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="PostgreSQL descartável")


def _proof(preview):
    return dict(
        expected_case_id=preview["case_id"],
        expected_version_id=preview["version_id"],
        expected_revision=preview["revision"],
        expected_proof_sha256=preview["proof_sha256"],
        confirm_identity_remains_private=True,
        confirm_zero_graph=True,
    )


def _publication(preview):
    return OrganisationPublicationRequest(
        **_proof(preview),
        rationale="Fonte oficial sintética verificada para publicação mínima.",
        public_rationale="Denominação e categoria confirmadas na fonte oficial sintética.",
        confirm_official_source=True,
        confirm_public_interest_and_minimisation=True,
        confirm_publication=True,
    )


def _withdrawal(preview):
    return OrganisationWithdrawalRequest(
        **_proof(preview),
        reason="OFFICIAL_SOURCE_CORRECTION",
        rationale="Retirada sintética documentada para testar o histórico imutável.",
        public_rationale="Correção da fonte oficial requer uma nova versão revista.",
        confirm_preserve_history_and_replies=True,
        confirm_withdrawal=True,
    )


async def _approve(repo, case_id, actor):
    editorial = EditorialRepository(repo.pool)
    await editorial.transition(
        case_id=case_id,
        action=EditorialAction.START_REVIEW,
        expected_revision=1,
        rationale="Início da revisão humana da prova oficial sintética.",
        source_confirmed=False,
        actor=actor,
    )
    return await editorial.transition(
        case_id=case_id,
        action=EditorialAction.APPROVE,
        expected_revision=2,
        rationale="Aprovação humana da prova oficial para este âmbito específico.",
        source_confirmed=True,
        actor=actor,
    )


async def _identity(repo, fiscal=None):
    payload, actor = await _fixture(repo)
    fiscal = fiscal or str(100_000_000 + uuid.uuid4().int % 899_999_999)
    payload = payload.model_copy(update={"fiscal_identifier": SecretStr(fiscal)})
    staged = await _stage(repo, payload, actor)
    identity_repo = BaseOrganisationEditorialRepository(repo.pool)
    candidate = await identity_repo.get_exact_candidate(
        observation_id=staged["observation_id"],
        source_record_sha256=staged["source_record_sha256"],
    )
    result = await identity_repo.create_proposal(payload=_request(candidate), actor=actor)
    case_id = result["case"]["id"]
    await _approve(repo, case_id, actor)
    await repo.pool.execute("UPDATE staff_profiles SET role='ADMIN' WHERE id=$1", actor.staff_id)
    return case_id, actor.model_copy(update={"role": StaffRole.ADMIN}), fiscal, staged


async def _prepare(repo, fiscal=None):
    identity_id, actor, fiscal, staged = await _identity(repo, fiscal)
    adapter = BaseOrganisationPublicationRepository(repo.pool)
    preview = await adapter.inspect_proposal(identity_case_id=identity_id)
    assert preview["eligible"] is True
    request = OrganisationPublicationProposalRequest(
        **_proof(preview),
        confirm_separate_review=True,
        confirm_no_publication=True,
    )
    proposal = await adapter.create_proposal(payload=request, actor=actor)
    case_id = proposal["case"]["id"]
    assert proposal["case"]["current_state"] == "PENDING"
    assert identity_id != case_id
    await _approve(repo, case_id, actor)
    return adapter, identity_id, case_id, actor, fiscal, staged


async def _counts(repo):
    return {
        name: await repo.pool.fetchval(f'SELECT COUNT(*) FROM "{name}"')
        for name in (
            "organisations",
            "base_public_organisation_publication_snapshots",
            "interest_entities",
            "public_contract_parties",
            "contract_match_reviews",
            "interest_relationships",
            "editorial_publication_events",
            "data_publication_reviews",
            "audit_events",
        )
    }


@pytest.mark.asyncio
async def test_separate_publication_withdrawal_republication_and_privacy(repository):
    repo = repository
    before = await _counts(repo)
    adapter, identity_id, case_id, actor, fiscal, staged = await _prepare(repo)
    assert (await _counts(repo))["organisations"] == before["organisations"]
    preview = await adapter.inspect_publication(case_id=case_id)
    assert preview["eligible"] is True
    result = await adapter.publish(case_id=case_id, payload=_publication(preview), actor=actor)
    public_id = result["public_id"]
    assert result["state"] == "PUBLISHED"
    after = await _counts(repo)
    for table in (
        "interest_entities",
        "public_contract_parties",
        "contract_match_reviews",
        "interest_relationships",
    ):
        assert after[table] == before[table]
    assert after["organisations"] == before["organisations"] + 1
    identity = await EditorialRepository(repo.pool).get_case(identity_id)
    assert identity["current_state"] == "APPROVED" and identity["publication_events"] == []
    private = await repo.pool.fetchrow(
        """SELECT protected_identifier_digest,observation_sha256,link_status,
                  publication_eligible
           FROM base_organisation_identity_observations WHERE id=$1""",
        staged["observation_id"],
    )
    assert private["link_status"] == "UNLINKED_PRIVATE" and private["publication_eligible"] is False
    serialised = json.dumps([preview, result, identity], default=str)
    for secret in (fiscal, private["protected_identifier_digest"], private["observation_sha256"]):
        assert secret not in serialised
    withdrawal = await adapter.inspect_withdrawal(case_id=case_id)
    withdrawn = await adapter.withdraw(
        case_id=case_id, payload=_withdrawal(withdrawal), actor=actor
    )
    assert withdrawn["history_preserved"] is True
    assert (
        await repo.pool.fetchval(
            "SELECT publication_status::text FROM organisations WHERE id=$1", public_id
        )
        == "WITHDRAWN"
    )
    second, _, second_case, second_actor, _, _ = await _prepare(repo, fiscal)
    second_preview = await second.inspect_publication(case_id=second_case)
    assert second_preview["public_fields"]["id"] == public_id
    second_result = await second.publish(
        case_id=second_case, payload=_publication(second_preview), actor=second_actor
    )
    assert second_result["public_record_sha256"] != result["public_record_sha256"]
    assert (
        await repo.pool.fetchval(
            """SELECT COUNT(*) FROM base_public_organisation_publication_snapshots
               WHERE organisation_id=$1""",
            public_id,
        )
        == 2
    )


@pytest.mark.asyncio
async def test_stale_confirmation_and_concurrent_publish_do_not_duplicate(repository):
    adapter, _, case_id, actor, _, _ = await _prepare(repository)
    preview = await adapter.inspect_publication(case_id=case_id)
    counts = await _counts(repository)
    bad = _publication(preview).model_copy(update={"expected_proof_sha256": "0" * 64})
    with pytest.raises(EditorialConflictError):
        await adapter.publish(case_id=case_id, payload=bad, actor=actor)
    assert await _counts(repository) == counts
    results = await asyncio.gather(
        *(
            adapter.publish(case_id=case_id, payload=_publication(preview), actor=actor)
            for _ in range(2)
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, EditorialConflictError) for result in results) == 1


@pytest.mark.asyncio
async def test_late_failure_rolls_back_all_publication_effects(repository, monkeypatch):
    adapter, _, case_id, actor, _, _ = await _prepare(repository)
    preview = await adapter.inspect_publication(case_id=case_id)
    counts = await _counts(repository)

    async def fail(*args, **kwargs):
        raise asyncpg.CheckViolationError("synthetic late failure")

    monkeypatch.setattr(adapter, "_decision", fail)
    with pytest.raises(EditorialConflictError):
        await adapter.publish(case_id=case_id, payload=_publication(preview), actor=actor)
    assert await _counts(repository) == counts


@pytest.mark.asyncio
async def test_sql_cannot_edit_snapshot_project_withdrawal_or_link_graph(repository):
    adapter, _, case_id, actor, _, _ = await _prepare(repository)
    preview = await adapter.inspect_publication(case_id=case_id)
    result = await adapter.publish(case_id=case_id, payload=_publication(preview), actor=actor)
    public_id = result["public_id"]
    for sql in (
        "UPDATE organisations SET legal_name='Outro nome' WHERE id=$1",
        "UPDATE organisations SET publication_status='WITHDRAWN' WHERE id=$1",
        "DELETE FROM organisations WHERE id=$1",
        """UPDATE base_public_organisation_publication_snapshots
           SET legal_name='Outro nome' WHERE organisation_id=$1""",
        "DELETE FROM base_public_organisation_publication_snapshots WHERE organisation_id=$1",
    ):
        async with repository.pool.acquire() as connection:
            with pytest.raises(asyncpg.PostgresError):
                async with connection.transaction():
                    await connection.execute(sql, public_id)
    async with repository.pool.acquire() as connection:
        with pytest.raises(asyncpg.PostgresError, match="não autoriza ligações"):
            async with connection.transaction():
                await connection.execute(
                    """INSERT INTO interest_entities
                       (id,kind,public_label,organisation_id,verification_status,
                        publication_status,created_at,updated_at)
                       VALUES ($1,'COMPANY','Ligação proibida',$2,'VERIFIED','PUBLISHED',
                        NOW(),NOW())""",
                    f"forbidden_graph_{uuid.uuid4().hex}",
                    public_id,
                )
    for protected_table in (
        "base_public_organisation_publication_snapshots",
        "audit_events",
        "data_publication_reviews",
        "editorial_publication_events",
    ):
        async with repository.pool.acquire() as connection:
            with pytest.raises(asyncpg.PostgresError):
                async with connection.transaction():
                    await connection.execute(f'TRUNCATE TABLE "{protected_table}"')
    assert (
        await repository.pool.fetchval(
            "SELECT publication_status::text FROM organisations WHERE id=$1", public_id
        )
        == "PUBLISHED"
    )


@pytest.mark.asyncio
async def test_admin_mfa_and_repeat_proposal_contract(repository):
    identity_id, actor, _, _ = await _identity(repository)
    adapter = BaseOrganisationPublicationRepository(repository.pool)
    preview = await adapter.inspect_proposal(identity_case_id=identity_id)
    request = OrganisationPublicationProposalRequest(
        **_proof(preview), confirm_separate_review=True, confirm_no_publication=True
    )
    first = await adapter.create_proposal(payload=request, actor=actor)
    with pytest.raises(EditorialConflictError):
        await adapter.create_proposal(payload=request, actor=actor)
    recovery = await adapter.inspect_proposal(identity_case_id=identity_id)
    assert recovery["existing_case_id"] == first["case"]["id"]
    await _approve(repository, first["case"]["id"], actor)
    preview = await adapter.inspect_publication(case_id=first["case"]["id"])
    for restricted in (
        actor.model_copy(update={"role": StaffRole.REVIEWER}),
        actor.model_copy(update={"assurance_level": "aal1"}),
    ):
        with pytest.raises(EditorialConflictError):
            await adapter.publish(
                case_id=first["case"]["id"], payload=_publication(preview), actor=restricted
            )


@pytest.mark.asyncio
async def test_public_projection_and_right_of_reply_preserve_private_identity(repository):
    adapter, _, case_id, actor, fiscal_identifier, staged = await _prepare(repository)
    preview = await adapter.inspect_publication(case_id=case_id)
    published = await adapter.publish(
        case_id=case_id,
        payload=_publication(preview),
        actor=actor,
    )
    public_id = published["public_id"]
    public = PublicOrganisationRepository(repository.pool)

    listing = await public.list(limit=100, offset=0)
    summary = next(item for item in listing["items"] if item["id"] == public_id)
    assert summary["public_record_sha256"] == published["public_record_sha256"]
    detail = await public.get(public_id=public_id)
    assert detail is not None
    assert detail["source"]["publisher"] == "IRN"
    assert detail["replies"] == []
    public_serialised = json.dumps([summary, detail], default=str)
    private = await repository.pool.fetchrow(
        """SELECT protected_identifier_digest,observation_sha256
           FROM base_organisation_identity_observations WHERE id=$1""",
        staged["observation_id"],
    )
    for secret in (
        fiscal_identifier,
        private["protected_identifier_digest"],
        private["observation_sha256"],
        staged["observation_id"],
    ):
        assert secret not in public_serialised

    reply = RightOfReplyRequest(
        target_type="ORGANISATION",
        target_id=public_id,
        original_record_sha256=published["public_record_sha256"],
        claimant_public_name="Organização Fictícia de Ensaio",
        claimant_role="Representante autorizado",
        statement_text=(
            "Resposta sintética suficientemente longa para verificar preservação e ligação exata."
        ),
        legitimacy_confirmed=True,
    )
    receipt = build_right_of_reply_receipt(reply, random_token=uuid.uuid4().hex[:12])
    await repository.save_right_of_reply(reply, receipt)
    invalid = reply.model_copy(update={"original_record_sha256": "0" * 64})
    with pytest.raises(ValueError, match="fotografia pública"):
        await repository.save_right_of_reply(
            invalid,
            build_right_of_reply_receipt(invalid, random_token=uuid.uuid4().hex[:12]),
        )
    await repository.pool.execute(
        "UPDATE rights_of_reply SET status='PUBLISHED' WHERE public_reference=$1",
        receipt.public_reference,
    )
    detail_with_reply = await public.get(public_id=public_id)
    assert detail_with_reply is not None
    assert [item["public_reference"] for item in detail_with_reply["replies"]] == [
        receipt.public_reference
    ]

    withdrawal = await adapter.inspect_withdrawal(case_id=case_id)
    await adapter.withdraw(case_id=case_id, payload=_withdrawal(withdrawal), actor=actor)
    assert await public.get(public_id=public_id) is None
    history = await public.history(public_id=public_id)
    assert history is not None
    assert [item["action"] for item in history["items"]] == ["PUBLISH", "WITHDRAW"]
    assert [item["public_reference"] for item in history["replies"]] == [receipt.public_reference]
    assert history["replies"][0]["original_record_sha256"] == published["public_record_sha256"]
    assert all(
        "legal_name" not in item and "observation_id" not in item for item in history["items"]
    )
    assert (
        await repository.pool.fetchval(
            "SELECT COUNT(*) FROM rights_of_reply WHERE public_reference=$1",
            receipt.public_reference,
        )
        == 1
    )


@pytest.mark.parametrize("text", [" " * 19 + "x", "\u00a0" * 19 + "x", "x" * 19 + " "])
def test_rationale_must_have_twenty_meaningful_characters(text):
    preview = {
        "case_id": "editorial_case_" + "a" * 32,
        "version_id": "editorial_version_" + "b" * 32,
        "revision": 3,
        "proof_sha256": "c" * 64,
    }
    for request in (_publication(preview), _withdrawal(preview)):
        data = request.model_dump()
        data["public_rationale"] = text
        with pytest.raises(ValidationError):
            type(request).model_validate(data)
