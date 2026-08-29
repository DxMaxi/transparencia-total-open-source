import hashlib
import json
import os
import uuid
from datetime import UTC, datetime

import asyncpg
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.models.editorial import (
    EditorialAction,
    ParliamentWithdrawalReason,
    StaffRole,
    StaffSession,
)
from app.models.ept_declaration import (
    EptExactIdentityLinkRequest,
    EptLegalAssessmentOutcome,
    EptLegalAssessmentRecordRequest,
    EptPublicInterestEditorialProposalRequest,
    EptPublicInterestObservationInput,
    EptPublicInterestPublicationRequest,
    EptPublicInterestWithdrawalRequest,
)
from app.repositories.editorial import EditorialRepository
from app.repositories.ept_declaration_editorial import EptDeclarationEditorialRepository
from app.repositories.ept_declaration_publication import (
    EptDeclarationPublicationGateRepository,
)
from app.repositories.ept_declaration_staging import EptDeclarationStagingRepository
from app.repositories.postgres import PostgresRepository

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


async def _insert_source_with_archive(
    connection: asyncpg.Connection,
    *,
    source_id: str,
    publisher: str,
    kind: str,
    official_identifier: str,
    url: str,
    now: datetime,
    content_sha256: str,
    suffix: str,
) -> None:
    await connection.execute(
        """
        INSERT INTO source_documents
            (id, publisher, kind, title, official_identifier, url,
             retrieved_at, published_at, content_sha256, mime_type,
             raw_storage_key, parser_version, created_at)
        VALUES ($1, $2::"SourcePublisher", $3::"DocumentKind",
                'Prova oficial descartável V5.47', $4, $5, $6, NULL, $7,
                'application/json', $8, 'ept-v5.47-test', NOW())
        """,
        source_id,
        publisher,
        kind,
        official_identifier,
        url,
        now.replace(tzinfo=None),
        content_sha256,
        f"sha256/{content_sha256[:2]}/{content_sha256}",
    )
    await connection.execute(
        """
        INSERT INTO source_archive_attestations
            (id, source_document_id, storage_backend, storage_key,
             content_sha256, byte_size, mime_type, retrieval_url,
             retrieved_at, archived_at, archived_by,
             attestation_sha256, created_at)
        VALUES ($1, $2, 'POSTGRES', $3, $4, 128, 'application/json',
                $5, $6, $6, 'test:v5.47', $7, NOW())
        """,
        f"archive_{source_id}",
        source_id,
        f"sha256/{content_sha256[:2]}/{content_sha256}",
        content_sha256,
        url,
        now.replace(tzinfo=None),
        hashlib.sha256(f"attestation:{suffix}:{source_id}".encode()).hexdigest(),
    )


@pytest.fixture
async def repository() -> PostgresRepository:
    repo = PostgresRepository(
        Settings(
            environment="test",
            protected_identifier_pepper=SecretStr("p" * 32),
        )
    )
    await repo.connect()
    try:
        yield repo
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_ept_gate_publishes_and_withdraws_without_deleting_history(
    repository: PostgresRepository,
) -> None:
    assert repository.pool is not None
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC).replace(microsecond=0)
    declaration_id = f"EPT-{suffix}"
    raw_subject_identifier = f"ept-subject-{suffix}"
    source_id = f"source_ept_gate_{suffix}"
    source_url = f"https://entidadetransparencia.pt/registos/{declaration_id}"
    source_sha256 = hashlib.sha256(f"ept:{suffix}".encode()).hexdigest()
    identity_source_id = f"source_identity_{suffix}"
    identity_source_url = f"https://www.parlamento.pt/Deputado/{suffix}"
    identity_source_sha256 = hashlib.sha256(f"identity:{suffix}".encode()).hexdigest()
    person_id = f"person_ept_{suffix}"
    person_source_id = f"AR-{suffix}"
    reviewer_auth = uuid.uuid4()
    admin_auth = uuid.uuid4()
    reviewer_id = f"staff_ept_reviewer_{suffix}"
    admin_id = f"staff_ept_admin_{suffix}"
    reviewer_alias = f"revisor-ept-{suffix}"
    admin_alias = f"admin-ept-{suffix}"

    async with repository.pool.acquire() as connection, connection.transaction():
        await _insert_source_with_archive(
            connection,
            source_id=source_id,
            publisher="TRANSPARENCY_ENTITY",
            kind="DECLARATION",
            official_identifier=declaration_id,
            url=source_url,
            now=now,
            content_sha256=source_sha256,
            suffix=suffix,
        )
        await _insert_source_with_archive(
            connection,
            source_id=identity_source_id,
            publisher="PARLIAMENT",
            kind="OPEN_DATASET",
            official_identifier=person_source_id,
            url=identity_source_url,
            now=now,
            content_sha256=identity_source_sha256,
            suffix=suffix,
        )
        await _prepare_disposable_auth_user(connection, reviewer_auth)
        await _prepare_disposable_auth_user(connection, admin_auth)
        await connection.execute(
            """
            INSERT INTO staff_profiles
                (id, auth_user_id, public_alias, role, active, created_at, updated_at)
            VALUES ($1, $2, $3, 'REVIEWER', TRUE, NOW(), NOW()),
                   ($4, $5, $6, 'ADMIN', TRUE, NOW(), NOW())
            """,
            reviewer_id,
            reviewer_auth,
            reviewer_alias,
            admin_id,
            admin_auth,
            admin_alias,
        )
        await connection.execute(
            """
            INSERT INTO people
                (id, source_id, full_name, parliamentary_name, slug, role,
                 active, created_at, updated_at)
            VALUES ($1, $2, 'Pessoa Pública de Teste', 'Pessoa de Teste', $3,
                    'DEPUTY', TRUE, NOW(), NOW())
            """,
            person_id,
            person_source_id,
            f"pessoa-ept-{suffix}",
        )
        await connection.execute(
            """
            INSERT INTO data_publication_reviews
                (id, entity_type, entity_id, purpose, legal_basis, sensitivity,
                 necessity_assessment, proportionality_test, publishable,
                 source_document_id, reviewed_by, reviewed_at)
            VALUES ($1, 'PERSON', $2, 'Identidade pública parlamentar de teste',
                    'PUBLIC_INTEREST', 'PUBLIC_PERSONAL',
                    'Identificador oficial exato numa fonte atestada.',
                    'Sem inferência por nome.', TRUE, $3, $4, NOW())
            """,
            f"person_review_{suffix}",
            person_id,
            identity_source_id,
            reviewer_alias,
        )

    staged = await EptDeclarationStagingRepository(
        repository.pool,
        repository.settings,
    ).stage_observation(
        payload=EptPublicInterestObservationInput(
            source_document_id=source_id,
            official_declaration_id=declaration_id,
            official_subject_identifier=SecretStr(raw_subject_identifier),
            public_subject_name="Pessoa Pública de Teste",
            declared_at=now,
            period_label="2026",
            confirm_public_interest_register_only=True,
            confirm_no_income_or_asset_content=True,
            confirm_no_protected_identifiers_persisted=True,
            confirm_private_only=True,
        ),
        actor_alias=reviewer_alias,
    )
    reviewer = StaffSession(
        staff_id=reviewer_id,
        auth_user_id=reviewer_auth,
        public_alias=reviewer_alias,
        role=StaffRole.REVIEWER,
        assurance_level="aal2",
        mfa_required=False,
    )
    admin = StaffSession(
        staff_id=admin_id,
        auth_user_id=admin_auth,
        public_alias=admin_alias,
        role=StaffRole.ADMIN,
        assurance_level="aal2",
        mfa_required=False,
    )
    editorial_adapter = EptDeclarationEditorialRepository(repository.pool)
    proposal = await editorial_adapter.create_proposal(
        payload=EptPublicInterestEditorialProposalRequest(
            observation_id=str(staged["observation_id"]),
            source_record_sha256=str(staged["source_record_sha256"]),
            confirm_private_only=True,
            confirm_public_interest_register_only=True,
            confirm_no_income_or_asset_content=True,
            confirm_no_name_matching=True,
            confirm_identity_unlinked=True,
            confirm_independent_legal_review_required=True,
        ),
        actor=reviewer,
    )
    case_id = str(proposal["case"]["id"])
    editorial = EditorialRepository(repository.pool)
    await editorial.transition(
        case_id=case_id,
        action=EditorialAction.START_REVIEW,
        expected_revision=1,
        rationale="A fonte individual e o âmbito serão revistos sem associação por nome.",
        source_confirmed=False,
        actor=reviewer,
    )
    approved = await editorial.transition(
        case_id=case_id,
        action=EditorialAction.APPROVE,
        expected_revision=2,
        rationale="A fonte EPT individual e o âmbito mínimo foram confirmados.",
        source_confirmed=True,
        actor=reviewer,
    )
    version = next(item for item in approved["versions"] if item["is_current"])
    gate = EptDeclarationPublicationGateRepository(repository.pool, repository.settings)
    initial_gate = await gate.inspect_gate(case_id=case_id)
    assert initial_gate["legal_assessment"] is None
    assert initial_gate["identity_link"] is None

    legal_result = await gate.record_legal_assessment(
        case_id=case_id,
        payload=EptLegalAssessmentRecordRequest(
            expected_case_id=case_id,
            expected_revision=3,
            expected_version_id=str(version["id"]),
            expected_version_sha256=str(version["normalized_sha256"]),
            expected_observation_id=str(staged["observation_id"]),
            expected_source_sha256=source_sha256,
            expected_source_record_sha256=str(staged["source_record_sha256"]),
            outcome=EptLegalAssessmentOutcome.PERMITS_PUBLIC_INTEREST_METADATA_ONLY,
            assessment_document_sha256=hashlib.sha256(f"legal:{suffix}".encode()).hexdigest(),
            assessment_document_storage_backend="OTHER_ENCRYPTED_PRIVATE",
            assessment_document_storage_key=SecretStr(f"legal/{suffix}.pdf.age"),
            assessment_document_byte_size=4096,
            assessment_document_mime_type="application/pdf",
            assessor_reference_sha256=hashlib.sha256(f"assessor:{suffix}".encode()).hexdigest(),
            qualification_evidence_sha256=hashlib.sha256(
                f"qualification:{suffix}".encode()
            ).hexdigest(),
            conflict_check_sha256=hashlib.sha256(f"conflict:{suffix}".encode()).hexdigest(),
            assessed_at=now,
            valid_until=None,
            recording_rationale="Documento cifrado e conclusão humana externa conferidos.",
            confirm_external_human_assessment=True,
            confirm_independent_assessor=True,
            confirm_qualification_and_conflicts_checked=True,
            confirm_public_interest_metadata_only=True,
            confirm_document_encrypted_and_private=True,
            confirm_system_did_not_issue_legal_opinion=True,
        ),
        actor=admin,
    )
    assert legal_result["created"] is True
    identity_result = await gate.record_identity_link(
        case_id=case_id,
        payload=EptExactIdentityLinkRequest(
            expected_case_id=case_id,
            expected_revision=3,
            expected_version_id=str(version["id"]),
            expected_version_sha256=str(version["normalized_sha256"]),
            expected_observation_id=str(staged["observation_id"]),
            expected_source_sha256=source_sha256,
            expected_source_record_sha256=str(staged["source_record_sha256"]),
            official_subject_identifier=SecretStr(raw_subject_identifier),
            person_id=person_id,
            expected_person_source_id=person_source_id,
            identity_evidence_document_id=identity_source_id,
            expected_identity_evidence_sha256=identity_source_sha256,
            recording_rationale=(
                "Identificador oficial exato confirmado em segunda fonte arquivada."
            ),
            confirm_exact_official_identifier=True,
            confirm_second_official_source_reviewed=True,
            confirm_no_name_or_fuzzy_matching=True,
            confirm_identifier_will_only_persist_as_hmac=True,
            confirm_same_person=True,
        ),
        actor=admin,
    )
    assert identity_result["created"] is True
    assert identity_result["raw_identifier_persisted"] is False

    preview = await gate.inspect_publication(case_id=case_id)
    assert preview["eligible"] is True
    assert preview["blockers"] == []
    assert raw_subject_identifier not in json.dumps(preview, ensure_ascii=False)
    legal = preview["legal_assessment"]
    identity = preview["identity_link"]
    assert isinstance(legal, dict)
    assert isinstance(identity, dict)
    published = await gate.publish(
        case_id=case_id,
        payload=EptPublicInterestPublicationRequest(
            expected_case_id=case_id,
            expected_revision=int(preview["case_revision"]),
            expected_version_id=str(preview["version_id"]),
            expected_version_sha256=str(preview["version_sha256"]),
            expected_observation_id=str(preview["observation_id"]),
            expected_source_sha256=source_sha256,
            expected_source_record_sha256=str(preview["source_record_sha256"]),
            expected_declaration_id=str(preview["declaration_id"]),
            expected_person_id=str(identity["person_id"]),
            expected_identity_link_id=str(identity["id"]),
            expected_identity_proof_sha256=str(identity["link_proof_sha256"]),
            expected_legal_assessment_id=str(legal["id"]),
            expected_legal_document_sha256=str(legal["document_sha256"]),
            expected_legal_assessment_proof_sha256=str(preview["legal_assessment_proof_sha256"]),
            expected_publication_proof_sha256=str(preview["publication_proof_sha256"]),
            rationale="Todas as portas documentais foram revistas pelo administrador.",
            public_rationale=(
                "Metadados mínimos publicados após revisão humana e jurídica independente."
            ),
            confirm_source_and_archive_reviewed=True,
            confirm_exact_identity_link_reviewed=True,
            confirm_independent_legal_assessment_reviewed=True,
            confirm_public_interest_metadata_only=True,
            confirm_no_income_asset_or_protected_identifier=True,
            confirm_append_only_publication=True,
            confirm_publication=True,
        ),
        actor=admin,
    )
    assert published["state"] == "PUBLISHED"

    withdrawal = await gate.inspect_withdrawal(case_id=case_id)
    assert withdrawal["eligible"] is True
    withdrawn = await gate.withdraw(
        case_id=case_id,
        payload=EptPublicInterestWithdrawalRequest(
            expected_case_id=case_id,
            expected_revision=int(withdrawal["case_revision"]),
            expected_version_id=str(withdrawal["version_id"]),
            expected_version_sha256=str(withdrawal["version_sha256"]),
            expected_declaration_id=str(withdrawal["declaration_id"]),
            expected_source_sha256=str(withdrawal["source_sha256"]),
            expected_publication_proof_sha256=str(withdrawal["publication_proof_sha256"]),
            expected_withdrawal_proof_sha256=str(withdrawal["withdrawal_proof_sha256"]),
            expected_public_review_id=str(withdrawal["public_review_id"]),
            expected_publication_audit_event_id=str(withdrawal["publication_audit_event_id"]),
            expected_publication_event_id=str(withdrawal["publication_event_id"]),
            expected_publication_event_sha256=str(withdrawal["publication_event_sha256"]),
            expected_public_effect_sha256=str(withdrawal["public_effect_sha256"]),
            rationale=(
                "A fonte oficial foi corrigida; a visibilidade deve cessar sem apagar histórico."
            ),
            public_rationale="Metadados retirados após correção documentada da fonte oficial.",
            reason_category=ParliamentWithdrawalReason.OFFICIAL_SOURCE_CORRECTION,
            confirm_source_and_publication_reviewed=True,
            confirm_public_effect_reviewed=True,
            confirm_declaration_and_history_preserved=True,
            confirm_identity_and_legal_records_preserved=True,
            confirm_withdrawal=True,
        ),
        actor=admin,
    )
    assert withdrawn["state"] == "WITHDRAWN"

    async with repository.pool.acquire() as connection:
        counts = await connection.fetchrow(
            """
            SELECT
              (SELECT COUNT(*) FROM asset_declaration_metadata WHERE id = $1) AS declarations,
              (SELECT COUNT(*) FROM ept_exact_identity_links WHERE case_id = $2) AS links,
              (SELECT COUNT(*) FROM ept_independent_legal_assessments WHERE case_id = $2) AS legal,
              (SELECT COUNT(*) FROM editorial_publication_events WHERE case_id = $2) AS events,
              (SELECT COUNT(*) FROM data_publication_reviews
               WHERE entity_type = 'ASSET_DECLARATION' AND entity_id = $1) AS reviews
            """,
            published["declaration_id"],
            case_id,
        )
        assert counts is not None
        assert dict(counts) == {
            "declarations": 1,
            "links": 1,
            "legal": 1,
            "events": 2,
            "reviews": 2,
        }
        latest_publishable = await connection.fetchval(
            """
            SELECT publishable FROM data_publication_reviews
            WHERE entity_type = 'ASSET_DECLARATION' AND entity_id = $1
            ORDER BY reviewed_at DESC, id DESC LIMIT 1
            """,
            published["declaration_id"],
        )
        serialized_private = await connection.fetchval(
            """
            SELECT concat_ws(' ', observation::text, identity_link::text,
                              legal_assessment::text, audit::text)
            FROM ept_public_interest_observations AS observation
            JOIN ept_exact_identity_links AS identity_link
              ON identity_link.observation_id = observation.id
            JOIN ept_independent_legal_assessments AS legal_assessment
              ON legal_assessment.observation_id = observation.id
            JOIN audit_events AS audit ON audit.entity_id IN (
                observation.id, identity_link.id, legal_assessment.id
            )
            WHERE observation.id = $1
            LIMIT 1
            """,
            staged["observation_id"],
        )
        browser_roles_have_access = await connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_roles
                WHERE rolname IN ('anon', 'authenticated')
                  AND (
                    has_table_privilege(
                        rolname, 'public.ept_exact_identity_links',
                        'SELECT,INSERT,UPDATE,DELETE'
                    ) OR has_table_privilege(
                        rolname, 'public.ept_independent_legal_assessments',
                        'SELECT,INSERT,UPDATE,DELETE'
                    )
                  )
            )
            """
        )
        assert latest_publishable is False
        assert browser_roles_have_access is False
        with pytest.raises(asyncpg.PostgresError, match="append-only"):
            async with connection.transaction():
                await connection.execute(
                    "UPDATE ept_exact_identity_links SET person_source_id = 'changed' "
                    "WHERE case_id = $1",
                    case_id,
                )
        with pytest.raises(asyncpg.PostgresError, match="append-only"):
            async with connection.transaction():
                await connection.execute(
                    "DELETE FROM ept_independent_legal_assessments WHERE case_id = $1",
                    case_id,
                )
    assert raw_subject_identifier not in str(serialized_private)
