"""Promoção controlada de contratos do staging privado BASE para revisão pública.

Este módulo NÃO publica nada por si só. Faz apenas a ponte entre o staging
append-only da V4.2 (base_staging.py) e o mecanismo genérico e já existente
de decisão humana em `PostgresRepository.review_publication`.

Fluxo completo, sempre com decisão humana explícita em cada passo:

    BaseContractSnapshot (staging, append-only)
        -> mark_base_batch_publication_eligible()   [decisão 1: o lote pode ser considerado]
        -> propose_base_contract_for_review()        [materializa candidato DRAFT, ainda não público]
        -> review_publication(publish=True)          [decisão 2: publicar este contrato em concreto]

Nenhuma função aqui cria uma correspondência entre uma parte contratante e
qualquer outra entidade de interesse já conhecida (deputados, titulares de
cargos, etc.). Isso pertence ao circuito separado de `ContractMatchReview`,
que exige revisão humana própria e não é criado automaticamente.
"""

import json
from datetime import UTC, datetime
from typing import Any


def _new_id(prefix: str) -> str:
    import uuid

    return f"{prefix}_{uuid.uuid4().hex}"


class BasePromotionRepositoryMixin:
    """Mixin do repositório PostgreSQL para a promoção de contratos BASE."""

    async def mark_base_batch_publication_eligible(
        self,
        *,
        batch_id: str,
        reviewed_by: str,
        eligible: bool = True,
    ) -> dict[str, Any]:
        """Decisão humana explícita: este LOTE pode entrar em consideração.

        Isto não publica nenhum contrato. Só destranca a possibilidade de
        propor contratos individuais desse lote para revisão. Reversível:
        pode ser chamado de novo com eligible=False sem apagar histórico.
        """
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        if not reviewed_by or not reviewed_by.strip():
            raise ValueError("A elegibilidade de um lote exige um revisor identificado")

        async with self.pool.acquire() as connection, connection.transaction():
            batch = await connection.fetchrow(
                """
                SELECT id, publication_eligible, contract_count, party_count
                FROM base_staging_batches WHERE id = $1
                """,
                batch_id,
            )
            if batch is None:
                raise ValueError("Lote de staging BASE não encontrado")

            before = dict(batch)
            # As colunas TIMESTAMP(3) desta tabela são "sem fuso horário"; o asyncpg
            # exige datetime naive para elas (mesma convenção de base_staging.py).
            reviewed_at = datetime.now(UTC).replace(tzinfo=None) if eligible else None
            await connection.execute(
                """
                UPDATE base_staging_batches
                SET publication_eligible = $2,
                    eligibility_reviewed_by = $3,
                    eligibility_reviewed_at = $4
                WHERE id = $1
                """,
                batch_id,
                eligible,
                reviewed_by if eligible else None,
                reviewed_at,
            )
            after = {
                "publication_eligible": eligible,
                "eligibility_reviewed_by": reviewed_by if eligible else None,
                "eligibility_reviewed_at": reviewed_at.isoformat() if reviewed_at else None,
            }
            await connection.execute(
                """
                INSERT INTO audit_events
                    (id, entity_type, entity_id, action, actor_alias,
                     before_json, after_json, reason, created_at)
                VALUES ($1, 'BaseStagingBatch', $2, $3, $4, $5::jsonb, $6::jsonb, $7, NOW())
                """,
                _new_id("audit"),
                batch_id,
                "MARKED_PUBLICATION_ELIGIBLE" if eligible else "MARKED_PUBLICATION_INELIGIBLE",
                reviewed_by,
                json.dumps(before, default=str, ensure_ascii=False),
                json.dumps(after, ensure_ascii=False),
                f"{batch['contract_count']} contratos / {batch['party_count']} partes no lote",
            )
        return after

    async def propose_base_contract_for_review(
        self,
        *,
        contract_snapshot_id: str,
        reviewer_alias: str,
    ) -> dict[str, Any]:
        """Materializa UM contrato do staging BASE como candidato DRAFT.

        Não publica nada — cria apenas registos com verification_status
        pendente e publication_status DRAFT, prontos para serem decididos
        via `review_publication(entity_type="PUBLIC_CONTRACT", ...)`.

        Exige que o lote de origem já tenha sido marcado como elegível
        (ver mark_base_batch_publication_eligible). Sem isso, recusa.
        """
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        if not reviewer_alias or not reviewer_alias.strip():
            raise ValueError("Propor um contrato para revisão exige um revisor identificado")

        async with self.pool.acquire() as connection, connection.transaction():
            snapshot = await connection.fetchrow(
                """
                SELECT
                    contract.id, contract.batch_id, contract.source_id, contract.object,
                    contract.procedure::text AS procedure, contract.cpv_code,
                    contract.base_value, contract.contract_value, contract.currency,
                    contract.decision_at, contract.signed_at, contract.published_at,
                    contract.execution_days,
                    batch.publication_eligible, batch.source_document_id
                FROM base_contract_snapshots contract
                JOIN base_staging_batches batch ON batch.id = contract.batch_id
                WHERE contract.id = $1
                """,
                contract_snapshot_id,
            )
            if snapshot is None:
                raise ValueError("Contrato em staging BASE não encontrado")
            if not snapshot["publication_eligible"]:
                raise ValueError(
                    "O lote de origem ainda não foi marcado como elegível para "
                    "publicação; chame mark_base_batch_publication_eligible primeiro"
                )

            existing = await connection.fetchval(
                "SELECT id FROM public_contracts WHERE source_id = $1",
                snapshot["source_id"],
            )
            if existing is not None:
                raise ValueError(
                    f"Este contrato já tem um registo público candidato/publicado (id={existing})"
                )

            parties = await connection.fetch(
                """
                SELECT id, ordinal, role::text AS role, source_name, protected_identifier_digest
                FROM base_contract_party_snapshots
                WHERE contract_snapshot_id = $1
                ORDER BY ordinal
                """,
                contract_snapshot_id,
            )

            public_contract_id = _new_id("contract")
            await connection.execute(
                """
                INSERT INTO public_contracts
                    (id, source_id, object, procedure, cpv_code, base_value,
                     contract_value, currency, decision_at, signed_at, published_at,
                     execution_days, source_document_id, verification_status,
                     publication_status, created_at, updated_at)
                VALUES
                    ($1, $2, $3, $4::"PublicContractProcedure", $5, $6, $7, $8, $9, $10,
                     $11, $12, $13, 'INGESTED', 'DRAFT', NOW(), NOW())
                """,
                public_contract_id,
                snapshot["source_id"],
                snapshot["object"],
                snapshot["procedure"],
                snapshot["cpv_code"],
                snapshot["base_value"],
                snapshot["contract_value"],
                snapshot["currency"],
                snapshot["decision_at"],
                snapshot["signed_at"],
                snapshot["published_at"],
                snapshot["execution_days"],
                snapshot["source_document_id"],
            )

            party_entity_ids: list[str] = []
            for party in parties:
                organisation_id = await self._find_or_create_base_party_organisation(
                    connection,
                    contract_snapshot_id=contract_snapshot_id,
                    ordinal=party["ordinal"],
                    source_name=party["source_name"],
                    protected_identifier_digest=party["protected_identifier_digest"],
                )
                entity_id = await self._find_or_create_interest_entity_for_organisation(
                    connection,
                    organisation_id=organisation_id,
                    public_label=party["source_name"],
                    kind="PUBLIC_BODY" if party["role"] == "CONTRACTING_AUTHORITY" else "COMPANY",
                )
                await connection.execute(
                    """
                    INSERT INTO public_contract_parties
                        (id, public_contract_id, interest_entity_id, role,
                         source_name, source_public_id, created_at)
                    VALUES ($1, $2, $3, $4::"ContractPartyRole", $5, $6, NOW())
                    """,
                    _new_id("contract_party"),
                    public_contract_id,
                    entity_id,
                    party["role"],
                    party["source_name"],
                    party["protected_identifier_digest"],
                )
                party_entity_ids.append(entity_id)

            after = {
                "public_contract_id": public_contract_id,
                "source_id": snapshot["source_id"],
                "party_entity_ids": party_entity_ids,
                "verification_status": "INGESTED",
                "publication_status": "DRAFT",
            }
            await connection.execute(
                """
                INSERT INTO audit_events
                    (id, entity_type, entity_id, action, actor_alias,
                     before_json, after_json, reason, created_at)
                VALUES ($1, 'PublicContract', $2, 'STAGING_PROPOSED_FOR_REVIEW', $3,
                        $4::jsonb, $5::jsonb, $6, NOW())
                """,
                _new_id("audit"),
                public_contract_id,
                reviewer_alias,
                json.dumps({"contract_snapshot_id": contract_snapshot_id}, ensure_ascii=False),
                json.dumps(after, ensure_ascii=False),
                "Materializado a partir do staging BASE; ainda não publicado. "
                "Requer review_publication(publish=True) para expor publicamente.",
            )
        return after

    async def _find_or_create_base_party_organisation(
        self,
        connection: Any,
        *,
        contract_snapshot_id: str,
        ordinal: int,
        source_name: str,
        protected_identifier_digest: str | None,
    ) -> str:
        """Encontra ou cria uma Organisation para uma parte contratante.

        Com digest (NIF/NIPC protegido): reutiliza por correspondência EXATA
        de digest — nunca por semelhança de nome. Sem digest: cria uma
        organização isolada a este contrato, sem tentar adivinhar se é "a
        mesma" que qualquer outra já registada (evita inferência a partir de
        nome, que a metodologia do projeto proíbe).
        """
        if protected_identifier_digest:
            source_id = f"base-party-digest:{protected_identifier_digest}"
            existing = await connection.fetchval(
                "SELECT id FROM organisations WHERE source_id = $1", source_id
            )
            if existing:
                return str(existing)
        else:
            source_id = f"base-contract-party:{contract_snapshot_id}:{ordinal}"

        organisation_id = _new_id("org")
        await connection.execute(
            """
            INSERT INTO organisations
                (id, source_id, legal_name, normalised_name, kind, public_nipc,
                 source_document_id, verification_status, created_at, updated_at)
            SELECT $1, $2, $3, $4, 'COMPANY', NULL, batch.source_document_id,
                   'PENDING_REVIEW', NOW(), NOW()
            FROM base_contract_snapshots contract
            JOIN base_staging_batches batch ON batch.id = contract.batch_id
            WHERE contract.id = $5
            """,
            organisation_id,
            source_id,
            source_name,
            _normalise_party_name(source_name),
            contract_snapshot_id,
        )
        return organisation_id

    async def _find_or_create_interest_entity_for_organisation(
        self,
        connection: Any,
        *,
        organisation_id: str,
        public_label: str,
        kind: str,
    ) -> str:
        existing = await connection.fetchval(
            "SELECT id FROM interest_entities WHERE organisation_id = $1", organisation_id
        )
        if existing:
            return str(existing)
        entity_id = _new_id("entity")
        await connection.execute(
            """
            INSERT INTO interest_entities
                (id, kind, public_label, organisation_id, verification_status,
                 publication_status, created_at, updated_at)
            VALUES ($1, $2::"InterestEntityKind", $3, $4, 'PENDING_REVIEW', 'DRAFT', NOW(), NOW())
            """,
            entity_id,
            kind,
            public_label,
            organisation_id,
        )
        return entity_id


def _normalise_party_name(value: str) -> str:
    return " ".join(value.strip().upper().split())
