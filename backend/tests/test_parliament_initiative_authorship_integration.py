import hashlib
import json
import os
import uuid
from datetime import UTC, datetime

import asyncpg
import pytest
from pydantic import HttpUrl

from app.core.config import Settings
from app.models.archive import PrivateRawDocument
from app.models.editorial import (
    EditorialAction,
    PoliticianInitiativeAuthorshipEditorialProposalRequest,
    PoliticianInitiativeAuthorshipPublicationRequest,
    StaffRole,
    StaffSession,
)
from app.repositories.editorial import EditorialConflictError, EditorialRepository
from app.repositories.parliament_activity import ParliamentActivityRepository
from app.repositories.parliament_initiative_authorship import (
    ParliamentInitiativeAuthorshipRepository,
)
from app.repositories.parliament_resource_normalization import (
    PrivateParliamentArchivedResourceProof,
)
from app.repositories.politician_initiative_authorship_editorial import (
    PoliticianInitiativeAuthorshipEditorialRepository,
)
from app.repositories.politician_initiative_authorship_publication import (
    PoliticianInitiativeAuthorshipPublicationRepository,
)
from app.repositories.postgres import PostgresRepository
from app.services.parliament_initiative_authorship import (
    ParliamentInitiativeAuthorshipNormalizer,
)
from app.services.parliament_resource_manifest import ParliamentResourceFormat
from app.services.parliament_resource_normalization import ParliamentResourceNormalizer
from app.services.parliament_source_catalogue import ParliamentCatalogueKind

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


def _proof(unique_value: str) -> PrivateParliamentArchivedResourceProof:
    initiative_id = str(100_000 + int(unique_value[:8], 16) % 900_000)
    official_deputy_id = str(int(unique_value[12:24], 16))
    unique_label = "".join(chr(ord("a") + int(character, 16)) for character in unique_value)
    resource_url = (
        "https://app.parlamento.pt/webutils/docs/doc.txt?"
        f"fich=IniciativasXVII_{unique_label}_json.txt&Inline=true"
    )
    content = json.dumps(
        {
            "Iniciativas": [
                {
                    "IniId": initiative_id,
                    "IniNr": "1/XVII/1",
                    "IniDescTipo": "Projeto de Lei",
                    "IniTitulo": "Iniciativa oficial descartável de integração",
                    "IniLinkTexto": (
                        f"/ActividadeParlamentar/Paginas/DetalheIniciativa.aspx?BID={initiative_id}"
                    ),
                    "iniAutorDeputados": {
                        "Iniciativas_AutoresDeputadosOut": [
                            {
                                "idCadastro": official_deputy_id,
                                "Nome": "Nome parlamentar observado na fonte",
                                "GP": "TESTE",
                            }
                        ]
                    },
                }
            ]
        },
        ensure_ascii=False,
    ).encode()
    digest = hashlib.sha256(content).hexdigest()
    document = PrivateRawDocument(
        source_url=HttpUrl(resource_url),
        retrieved_at=datetime.now(UTC).replace(microsecond=0),
        content_sha256=digest,
        mime_type="application/json",
        content=content,
    )
    return PrivateParliamentArchivedResourceProof(
        archive_snapshot_id=f"official_index_{uuid.uuid4().hex}",
        archive_source_document_id="resolved-after-private-normalisation",
        parent_manifest_snapshot_id=f"official_index_{uuid.uuid4().hex}",
        parent_catalogue_snapshot_id=f"official_index_{uuid.uuid4().hex}",
        catalogue_kind=ParliamentCatalogueKind.INITIATIVES,
        legislature="XVII",
        resource_format=ParliamentResourceFormat.JSON,
        official_label="IniciativasXVII_json.txt",
        resource_url=resource_url,
        content_sha256=digest,
        byte_size=len(content),
        raw_document=document,
        manifest_content_sha256="d" * 64,
        catalogue_content_sha256="e" * 64,
        archive_attested=True,
    )


@pytest.fixture
async def repository() -> ParliamentInitiativeAuthorshipRepository:
    repo = ParliamentInitiativeAuthorshipRepository(Settings(environment="test"))
    await repo.connect()
    try:
        yield repo
    finally:
        await repo.close()


@pytest.mark.asyncio
async def test_authorship_snapshot_and_pending_case_are_private_append_only_and_idempotent(
    repository: ParliamentInitiativeAuthorshipRepository,
) -> None:
    assert repository.pool is not None
    unique_value = uuid.uuid4().hex
    proof = _proof(unique_value)
    initiative_collection = ParliamentResourceNormalizer().normalise(proof)
    authorship_collection = ParliamentInitiativeAuthorshipNormalizer().normalise(proof)

    archive_receipt = await repository.archive_raw_document(raw_document=proof.raw_document)
    initiatives = await ParliamentActivityRepository(repository.pool).persist(
        initiative_collection.dataset,
        archive_receipt=archive_receipt,
        archived_by="parliament-initiative-authorship-integration",
    )
    source_document_id = initiatives.source_document_id
    stored = await repository.persist_private_authorships(
        authorship_collection.dataset,
        source_document_id=source_document_id,
    )
    repeated = await repository.persist_private_authorships(
        authorship_collection.dataset,
        source_document_id=source_document_id,
    )
    snapshot_id = str(stored["normalised_snapshot_id"])

    assert stored["snapshot_created"] is True
    assert repeated["snapshot_created"] is False
    assert repeated["observations_written"] == 0
    assert stored["initiative_count"] == 1
    assert stored["authorship_count"] == 1
    assert stored["deputy_count"] == 1
    assert stored["people_created"] == 0
    assert stored["editorial_cases_created"] == 0
    assert stored["publication_performed"] is False

    observation = authorship_collection.dataset.observations[0]
    person_id = f"person_authorship_{uuid.uuid4().hex}"
    person_slug = f"pessoa-autoria-{uuid.uuid4().hex}"
    staff_id = f"staff_authorship_{uuid.uuid4().hex}"
    auth_user_id = uuid.uuid4()
    alias = f"revisor-authorship-{uuid.uuid4().hex[:12]}"
    async with repository.pool.acquire() as connection, connection.transaction():
        await _prepare_disposable_auth_user(connection, auth_user_id)
        await connection.execute(
            """
            INSERT INTO people
                (id, source_id, full_name, parliamentary_name, slug, role,
                 active, created_at, updated_at)
            VALUES ($1, $2, 'Nome deliberadamente diferente', NULL, $3,
                    'DEPUTY', TRUE, NOW(), NOW())
            """,
            person_id,
            observation.official_deputy_id,
            person_slug,
        )
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
        people_before = int(await connection.fetchval("SELECT COUNT(*) FROM people"))
        reviews_before = int(
            await connection.fetchval("SELECT COUNT(*) FROM data_publication_reviews")
        )

    actor = StaffSession(
        staff_id=staff_id,
        auth_user_id=auth_user_id,
        public_alias=alias,
        role=StaffRole.REVIEWER,
        assurance_level="aal1",
        mfa_required=False,
    )
    adapter = PoliticianInitiativeAuthorshipEditorialRepository(repository.pool)
    candidates = await adapter.list_candidates(
        legislature="XVII",
        query=observation.initiative_source_id,
        limit=20,
        offset=0,
    )
    candidate = next(item for item in candidates["items"] if item["snapshot_id"] == snapshot_id)
    assert candidate["proposal_eligible"] is True
    assert candidate["publication_ready"] is False
    assert candidate["identity_reconciliation"]["exact_identity"] is True
    assert candidate["identity_reconciliation"]["reviewed_identity"] is False
    assert candidate["identity_reconciliation"]["full_name"] == ("Nome deliberadamente diferente")
    assert candidate["name_matching_allowed"] is False
    assert candidate["party_matching_allowed"] is False

    payload = PoliticianInitiativeAuthorshipEditorialProposalRequest(
        observation_id=str(candidate["observation_id"]),
        source_record_sha256=str(candidate["source_record_sha256"]),
        confirm_private_only=True,
        confirm_exact_initiative_id=True,
        confirm_exact_official_deputy_id=True,
        confirm_official_author_relation=True,
        confirm_no_name_or_party_matching=True,
        confirm_no_collective_position_inference=True,
    )
    created = await adapter.create_proposal(payload=payload, actor=actor)
    repeated_case = await adapter.create_proposal(payload=payload, actor=actor)
    assert created["created"] is True
    assert repeated_case["created"] is False
    assert repeated_case["case"]["id"] == created["case"]["id"]
    assert created["case"]["subject_type"] == "PARLIAMENT_INITIATIVE_AUTHORSHIP"
    assert created["case"]["current_state"] == "PENDING"
    assert created["initiative_authorship_created"] is False
    assert created["publication_performed"] is False

    case_id = str(created["case"]["id"])
    editorial = EditorialRepository(repository.pool)
    await editorial.transition(
        case_id=case_id,
        action=EditorialAction.START_REVIEW,
        expected_revision=1,
        rationale="A relação IniId e idCadastro será comparada com o documento arquivado.",
        source_confirmed=False,
        actor=actor,
    )
    await editorial.transition(
        case_id=case_id,
        action=EditorialAction.APPROVE,
        expected_revision=2,
        rationale="A relação literal, o documento, a data e os hashes foram revistos.",
        source_confirmed=True,
        actor=actor,
    )

    async with repository.pool.acquire() as connection:
        assert int(await connection.fetchval("SELECT COUNT(*) FROM people")) == people_before
        assert (
            int(await connection.fetchval("SELECT COUNT(*) FROM data_publication_reviews"))
            == reviews_before
        )
        publication_events = int(
            await connection.fetchval(
                "SELECT COUNT(*) FROM editorial_publication_events WHERE case_id = $1",
                case_id,
            )
        )
        assert publication_events == 0
        with pytest.raises(asyncpg.PostgresError, match="append-only"):
            await connection.execute(
                "UPDATE parliament_initiative_author_observations "
                "SET parliamentary_name = 'Alterado' WHERE snapshot_id = $1",
                snapshot_id,
            )
        with pytest.raises(asyncpg.PostgresError, match="append-only"):
            await connection.execute(
                "DELETE FROM parliament_initiative_author_snapshots WHERE id = $1",
                snapshot_id,
            )

    admin_staff_id = f"staff_authorship_admin_{uuid.uuid4().hex}"
    admin_auth_user_id = uuid.uuid4()
    admin_alias = f"admin-authorship-{uuid.uuid4().hex[:12]}"
    membership_id = f"membership_authorship_{uuid.uuid4().hex}"
    async with repository.pool.acquire() as connection, connection.transaction():
        await _prepare_disposable_auth_user(connection, admin_auth_user_id)
        await connection.execute(
            """
            INSERT INTO staff_profiles
                (id, auth_user_id, public_alias, role, active, created_at, updated_at)
            VALUES ($1, $2, $3, 'ADMIN', TRUE, NOW(), NOW())
            """,
            admin_staff_id,
            admin_auth_user_id,
            admin_alias,
        )
        await connection.execute(
            """
            INSERT INTO parliamentary_membership_snapshots
                (id, person_id, parliamentary_name, full_name, party_id,
                 legislature, constituency, observed_at, source_document_id)
            VALUES ($1, $2, 'Nome parlamentar observado na fonte',
                    'Nome deliberadamente diferente', NULL, 'XVII',
                    'Dados indisponíveis', NOW(), $3)
            """,
            membership_id,
            person_id,
            source_document_id,
        )
        await connection.execute(
            """
            INSERT INTO data_publication_reviews
                (id, entity_type, entity_id, purpose, legal_basis, sensitivity,
                 necessity_assessment, proportionality_test, publishable,
                 source_document_id, reviewed_by, reviewed_at)
            VALUES ($1, 'PERSON', $2, 'Identidade parlamentar oficial',
                    'PUBLIC_INTEREST', 'PUBLIC_PERSONAL',
                    'O idCadastro e a fonte oficial foram revistos.',
                    'Publica apenas a identidade necessária.', TRUE, $3, $4, NOW()),
                   ($5, 'PARLIAMENT_ACTIVITY_SNAPSHOT', $6,
                    'Fotografia oficial de atividade parlamentar',
                    'PUBLIC_INTEREST', 'PUBLIC_OFFICIAL',
                    'A iniciativa e o manifesto foram revistos.',
                    'Publica apenas a fotografia aprovada.', TRUE, $3, $4, NOW())
            """,
            f"review_person_authorship_{uuid.uuid4().hex}",
            person_id,
            source_document_id,
            admin_alias,
            f"review_activity_authorship_{uuid.uuid4().hex}",
            initiatives.snapshot_id,
        )

    admin = StaffSession(
        staff_id=admin_staff_id,
        auth_user_id=admin_auth_user_id,
        public_alias=admin_alias,
        role=StaffRole.ADMIN,
        assurance_level="aal2",
        mfa_required=True,
    )
    publisher = PoliticianInitiativeAuthorshipPublicationRepository(repository.pool)
    preview = await publisher.inspect(case_id=case_id)
    assert preview["eligible"] is True, preview["blockers"]
    assert preview["publication_proof_sha256"] is not None
    public_initiative = preview["initiative"]
    assert isinstance(public_initiative, dict)
    assert public_initiative["number"] == "1/XVII/1"
    assert preview["authorship"]["relation"] == "AUTHOR"
    publication_payload = PoliticianInitiativeAuthorshipPublicationRequest(
        expected_case_id=case_id,
        expected_version_id=str(preview["version_id"]),
        expected_version_sha256=str(preview["version_sha256"]),
        expected_source_sha256=proof.content_sha256,
        expected_source_record_sha256=str(candidate["source_record_sha256"]),
        expected_activity_snapshot_sha256=str(public_initiative["activity_snapshot_sha256"]),
        expected_publication_proof_sha256=str(preview["publication_proof_sha256"]),
        rationale=("A relação AUTHOR, os dois identificadores e os dois arquivos foram revistos."),
        public_rationale=(
            "A Assembleia identifica esta pessoa como autora desta iniciativa pelo id oficial."
        ),
        confirm_source_reviewed=True,
        confirm_exact_official_ids_only=True,
        confirm_official_author_relation=True,
        confirm_public_initiative_reviewed=True,
        confirm_no_name_or_party_matching=True,
        confirm_no_collective_position_inference=True,
        confirm_append_only_publication=True,
        confirm_publication=True,
    )

    invalid_payload = publication_payload.model_copy(
        update={"expected_source_record_sha256": "f" * 64}
    )
    async with repository.pool.acquire() as connection:
        rows_before = int(
            await connection.fetchval("SELECT COUNT(*) FROM politician_initiative_authorships")
        )
        events_before = int(
            await connection.fetchval(
                "SELECT COUNT(*) FROM editorial_publication_events WHERE case_id = $1",
                case_id,
            )
        )
    with pytest.raises(EditorialConflictError):
        await publisher.publish(case_id=case_id, payload=invalid_payload, actor=admin)
    async with repository.pool.acquire() as connection:
        assert (
            int(await connection.fetchval("SELECT COUNT(*) FROM politician_initiative_authorships"))
            == rows_before
        )
        assert (
            int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM editorial_publication_events WHERE case_id = $1",
                    case_id,
                )
            )
            == events_before
        )

    published = await publisher.publish(
        case_id=case_id,
        payload=publication_payload,
        actor=admin,
    )
    authorship_id = str(published["authorship_id"])
    assert published["state"] == "PUBLISHED"
    assert published["people_created"] == 0
    assert published["initiatives_created"] == 0
    assert published["party_links_created"] == 0
    with pytest.raises(EditorialConflictError):
        await publisher.publish(case_id=case_id, payload=publication_payload, actor=admin)

    async with repository.pool.acquire() as connection:
        stored_authorship = await connection.fetchrow(
            """
            SELECT person_id, initiative_id, source_observation_id, relation,
                   source_document_id, source_record_sha256
            FROM politician_initiative_authorships WHERE id = $1
            """,
            authorship_id,
        )
        assert stored_authorship is not None
        assert stored_authorship["person_id"] == person_id
        assert stored_authorship["source_observation_id"] == candidate["observation_id"]
        assert stored_authorship["relation"] == "AUTHOR"
        assert stored_authorship["source_document_id"] == source_document_id
        assert stored_authorship["source_record_sha256"] == candidate["source_record_sha256"]
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM data_publication_reviews "
                "WHERE entity_type = 'POLITICIAN_INITIATIVE_AUTHORSHIP' "
                "AND entity_id = $1 AND publishable = TRUE",
                authorship_id,
            )
            == 1
        )
        assert (
            await connection.fetchval(
                "SELECT COUNT(*) FROM audit_events "
                "WHERE entity_type = 'POLITICIAN_INITIATIVE_AUTHORSHIP' "
                "AND entity_id = $1 AND action = 'PUBLISHED'",
                authorship_id,
            )
            == 1
        )
        with pytest.raises(asyncpg.PostgresError, match="append-only"):
            async with connection.transaction():
                await connection.execute(
                    "UPDATE politician_initiative_authorships "
                    "SET relation = 'AUTHOR' WHERE id = $1",
                    authorship_id,
                )

    public_repository = PostgresRepository(Settings(environment="test"))
    public_repository.pool = repository.pool
    public_profile = await public_repository.get_public_politician(person_slug)
    assert public_profile is not None
    assert len(public_profile["initiatives"]) == 1
    assert public_profile["initiatives"][0]["relation"] == "AUTHOR"
    assert public_profile["initiatives"][0]["number"] == "1/XVII/1"
    assert public_profile["coverage"]["initiatives"]["state"] == "AVAILABLE"
