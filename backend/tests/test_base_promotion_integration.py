"""Teste de integração real do circuito de promoção BASE (staging -> revisão -> público).

Ao contrário dos restantes testes de staging BASE (que usam pools falsos para
testar barreiras sem tocar em base de dados nenhuma), este teste exige um
PostgreSQL real e descartável — é o primeiro do projeto a fazê-lo. Fica
automaticamente ignorado se DATABASE_URL não estiver definido, para nunca
bloquear `pytest` num ambiente sem Postgres (ex.: máquina de desenvolvimento
sem serviço de base de dados a correr).

Para correr localmente:
    createdb tt_test_promotion
    export DATABASE_URL=postgresql://user:pass@localhost/tt_test_promotion
    # aplicar as 6 migrações de prisma/migrations em ordem, depois:
    pytest backend/tests/test_base_promotion_integration.py -v
"""

import os
import uuid

import pytest

from app.core.config import Settings
from app.repositories.postgres import PostgresRepository

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="Teste de integração real: exige DATABASE_URL para um PostgreSQL descartável",
)


@pytest.fixture
async def repo() -> PostgresRepository:
    settings = Settings()
    repository = PostgresRepository(settings)
    await repository.connect()
    try:
        yield repository
    finally:
        await repository.close()


async def _seed_evidence_chain(repo: PostgresRepository) -> dict[str, str]:
    """Cria a cadeia oficial completa (documento -> atestação -> sync_run -> lote ->
    contrato -> parte), do mesmo modo que store_base_collection faria, mas com SQL
    direto para isolar este teste da lógica de ingestão (já testada em
    test_base_persistence_guard.py)."""
    suffix = uuid.uuid4().hex[:12]
    sha = uuid.uuid4().hex + uuid.uuid4().hex[:32]  # 64 carateres hex
    url = f"https://dados.gov.pt/pt/datasets/teste-{suffix}"

    async with repo.pool.acquire() as conn, conn.transaction():
        await conn.execute(
            """INSERT INTO source_documents
               (id, publisher, kind, title, url, retrieved_at, content_sha256)
               VALUES ($1, 'BASE_GOV', 'OPEN_DATASET', 'teste', $2, NOW(), $3)""",
            f"doc_{suffix}", url, sha,
        )
        await conn.execute(
            """INSERT INTO source_archive_attestations
               (id, source_document_id, storage_backend, storage_key, content_sha256,
                byte_size, retrieval_url, retrieved_at, archived_at, archived_by,
                attestation_sha256)
               VALUES ($1, $2, 'LOCAL_FS', $3, $4, 1000, $5, NOW(), NOW(), 'teste', $4)""",
            f"att_{suffix}", f"doc_{suffix}", f"sha256/{sha[:2]}/{sha}", sha, url,
        )
        await conn.execute(
            """INSERT INTO sync_runs (id, source_name, dataset_url, status, code_version)
               VALUES ($1, 'BASE_GOV', $2, 'SUCCEEDED', 'test-parser')""",
            f"run_{suffix}", url,
        )
        await conn.execute(
            """INSERT INTO base_staging_batches
               (id, source_document_id, sync_run_id, resource_year, resource_title,
                resource_format, parser_version, normalised_sha256,
                identifier_digests_stored, contract_count, party_count, collected_at)
               VALUES ($1, $2, $3, 2025, 'teste', 'JSON', 'test-parser', $4, true, 1, 1, NOW())""",
            f"batch_{suffix}", f"doc_{suffix}", f"run_{suffix}", sha,
        )
        await conn.execute(
            """INSERT INTO base_contract_snapshots (id, batch_id, source_id, object, currency)
               VALUES ($1, $2, $3, 'objeto de teste', 'EUR')""",
            f"contract_{suffix}", f"batch_{suffix}", f"BASE-TEST-{suffix}",
        )
        await conn.execute(
            """INSERT INTO base_contract_party_snapshots
               (id, contract_snapshot_id, ordinal, role, source_name,
                protected_identifier_digest)
               VALUES ($1, $2, 0, 'CONTRACTOR', 'Fornecedor de Teste, Lda.', $3)""",
            f"party_{suffix}", f"contract_{suffix}", sha,
        )
    return {"batch_id": f"batch_{suffix}", "contract_snapshot_id": f"contract_{suffix}"}


@pytest.mark.asyncio
async def test_propose_before_eligible_is_rejected(repo: PostgresRepository) -> None:
    ids = await _seed_evidence_chain(repo)
    with pytest.raises(ValueError, match="elegível"):
        await repo.propose_base_contract_for_review(
            contract_snapshot_id=ids["contract_snapshot_id"], reviewer_alias="teste"
        )


@pytest.mark.asyncio
async def test_full_promotion_and_withdrawal_cycle(repo: PostgresRepository) -> None:
    ids = await _seed_evidence_chain(repo)

    await repo.mark_base_batch_publication_eligible(
        batch_id=ids["batch_id"], reviewed_by="editor-teste"
    )

    proposal = await repo.propose_base_contract_for_review(
        contract_snapshot_id=ids["contract_snapshot_id"], reviewer_alias="editor-teste"
    )
    assert proposal["publication_status"] == "DRAFT"

    # Não pode ser proposto duas vezes.
    with pytest.raises(ValueError, match="já tem um registo"):
        await repo.propose_base_contract_for_review(
            contract_snapshot_id=ids["contract_snapshot_id"], reviewer_alias="editor-teste"
        )

    decision = await repo.review_publication(
        entity_type="PUBLIC_CONTRACT",
        entity_id=proposal["public_contract_id"],
        publish=True,
        reviewer_alias="editor-teste",
        rationale="Contrato oficial verificado para efeitos de teste.",
    )
    assert decision["publishable"] is True

    async with repo.pool.acquire() as conn:
        published = await conn.fetchrow(
            "SELECT publication_status FROM public_contracts WHERE id = $1",
            proposal["public_contract_id"],
        )
    assert published["publication_status"] == "PUBLISHED"

    withdrawal = await repo.review_publication(
        entity_type="PUBLIC_CONTRACT",
        entity_id=proposal["public_contract_id"],
        publish=False,
        reviewer_alias="editor-teste",
        rationale="Retirada de teste; o registo deve continuar a existir.",
    )
    assert withdrawal["publishable"] is False

    async with repo.pool.acquire() as conn:
        withdrawn = await conn.fetchrow(
            "SELECT publication_status FROM public_contracts WHERE id = $1",
            proposal["public_contract_id"],
        )
        audit_count = await conn.fetchval(
            "SELECT count(*) FROM audit_events WHERE entity_id = $1",
            proposal["public_contract_id"],
        )
    assert withdrawn["publication_status"] == "WITHDRAWN"
    assert audit_count == 3  # proposto -> publicado -> retirado, nada apagado


@pytest.mark.asyncio
async def test_batch_data_columns_stay_immutable_after_eligibility_update(
    repo: PostgresRepository,
) -> None:
    """A decisão de elegibilidade não pode ser usada como porta lateral para
    alterar os dados recolhidos do lote."""
    ids = await _seed_evidence_chain(repo)
    await repo.mark_base_batch_publication_eligible(
        batch_id=ids["batch_id"], reviewed_by="editor-teste"
    )
    async with repo.pool.acquire() as conn:
        with pytest.raises(Exception, match="append-only"):
            await conn.execute(
                "UPDATE base_staging_batches SET contract_count = 999 WHERE id = $1",
                ids["batch_id"],
            )
