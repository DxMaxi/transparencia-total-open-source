"""Candidatos privados entre partes BASE e organizações por identificador exato."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import asyncpg

from app.models.base_contract_organisation_match import (
    BaseContractOrganisationMatchCandidateRequest,
)
from app.models.base_organisation import safe_registry_text
from app.models.editorial import StaffRole, StaffSession, validate_normalized_data
from app.repositories.editorial import (
    EditorialConflictError,
    EditorialNotFoundError,
    EditorialSourceError,
)

_SCHEMA_VERSION = "v5.54-base-contract-organisation-match-candidate/v1"
_EXACT_METHOD = "EXACT_PROTECTED_IDENTIFIER"
_PENDING_DECISION = "PENDING_REVIEW"
_PUBLIC_CONTRACT_ID = re.compile(r"^base_contract_[0-9a-f]{64}$")
_CONTRACT_PUBLICATION_ID = re.compile(r"^base_contract_publication_[0-9a-f]{32}$")
_PUBLIC_ORGANISATION_ID = re.compile(r"^base_public_org_[0-9a-f]{32}$")
_ORGANISATION_PUBLICATION_ID = re.compile(r"^base_org_publication_[0-9a-f]{32}$")
_OPAQUE_ID = re.compile(r"^[A-Za-z0-9_-]{1,200}$")
_RULE = (
    "Só um HMAC privado exatamente igual, com contrato e organização publicados e duas fontes "
    "oficiais arquivadas, pode originar um candidato privado PENDING_REVIEW."
)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _iso(value: object, *, label: str = "A data") -> str:
    if not isinstance(value, datetime):
        raise EditorialSourceError(f"{label} deixou de ter um formato temporal válido")
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _digest(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise EditorialSourceError(f"{label} deixou de ser um SHA-256 válido")
    cleaned = value.strip()
    if len(cleaned) != 64 or any(character not in "0123456789abcdef" for character in cleaned):
        raise EditorialSourceError(f"{label} deixou de ser um SHA-256 válido")
    return cleaned


def _exact_text(value: object, *, expected: str, label: str) -> str:
    if not isinstance(value, str) or value != expected:
        raise EditorialSourceError(f"{label} deixou de corresponder à fonte oficial esperada")
    return value


def _identifier(
    value: object,
    *,
    pattern: re.Pattern[str],
    label: str,
) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise EditorialSourceError(f"{label} deixou de ser uma referência válida")
    return value


def _count(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EditorialSourceError(f"{label} deixou de ser uma contagem válida")
    return value


def _official_url(value: object, *, publisher: str) -> str:
    if not isinstance(value, str):
        raise EditorialSourceError("O URL da fonte deixou de ser texto")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise EditorialSourceError("O URL da fonte oficial deixou de ser seguro") from None
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.fragment
    ):
        raise EditorialSourceError("O URL da fonte oficial deixou de ser seguro")
    if publisher == "BASE_GOV":
        if parsed.hostname != "dados.gov.pt":
            raise EditorialSourceError("A fonte contratual deixou de pertencer a dados.gov.pt")
    elif publisher == "JUSTICE_REGISTRY":
        if (
            parsed.hostname != "publicacoes.mj.pt"
            or parsed.path != "/DetalhePublicacao.aspx"
            or parsed.query
        ):
            raise EditorialSourceError("A fonte organizacional deixou de ser o ato exato do IRN")
    else:
        raise EditorialSourceError("O editor de fonte não é autorizado nesta correspondência")
    return value


def _safe_text(value: object, *, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise EditorialSourceError(f"{label} deixou de ser texto")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > maximum:
        raise EditorialSourceError(f"{label} deixou de ter um comprimento permitido")
    try:
        safe_registry_text(cleaned, max_length=maximum)
        validate_normalized_data({label: cleaned})
    except ValueError as exc:
        raise EditorialSourceError(f"{label} contém informação protegida") from exc
    return cleaned


def _candidate_proof(row: Mapping[str, Any]) -> str:
    return _sha256_json(
        {
            "schema_version": _SCHEMA_VERSION,
            "public_contract_id": row["public_contract_id"],
            "contract_publication_snapshot_id": row["contract_publication_snapshot_id"],
            "contract_party_snapshot_id": row["contract_party_snapshot_id"],
            "organisation_id": row["organisation_id"],
            "organisation_publication_snapshot_id": row["organisation_publication_snapshot_id"],
            "organisation_identity_observation_id": row["organisation_identity_observation_id"],
            "contract_source_document_id": row["contract_source_document_id"],
            "organisation_source_document_id": row["organisation_source_document_id"],
            "contract_source_record_sha256": _digest(
                row["contract_source_record_sha256"], label="A prova do contrato"
            ),
            "organisation_source_record_sha256": _digest(
                row["organisation_source_record_sha256"], label="A prova da organização"
            ),
            "contract_source_sha256": _digest(
                row["contract_source_sha256"], label="A fonte do contrato"
            ),
            "organisation_source_sha256": _digest(
                row["organisation_source_sha256"], label="A fonte da organização"
            ),
            "contract_archive_attestation_sha256": _digest(
                row["contract_archive_attestation_sha256"],
                label="O arquivo do contrato",
            ),
            "organisation_archive_attestation_sha256": _digest(
                row["organisation_archive_attestation_sha256"],
                label="O arquivo da organização",
            ),
            "contract_publication_proof_sha256": _digest(
                row["contract_publication_proof_sha256"],
                label="A publicação do contrato",
            ),
            "organisation_publication_proof_sha256": _digest(
                row["organisation_publication_proof_sha256"],
                label="A publicação da organização",
            ),
            "method": "EXACT_PROTECTED_IDENTIFIER",
            "decision": "PENDING_REVIEW",
            "two_active_publications": True,
            "independent_official_sources": True,
            "protected_identifier_compared_privately": True,
            "protected_identifier_exposed": False,
            "name_matching_used": False,
            "fuzzy_matching_used": False,
            "public_party_created": False,
            "match_review_created": False,
            "public_relationship_created": False,
        }
    )


_CONTRACT_SQL = """
SELECT contract.id AS public_contract_id,
       contract.source_id AS official_contract_id,
       contract.object AS contract_object,
       publication.id AS contract_publication_snapshot_id,
       publication.contract_snapshot_id,
       publication.source_document_id AS contract_source_document_id,
       publication.source_record_sha256 AS contract_source_record_sha256,
       publication.publication_proof_sha256 AS contract_publication_proof_sha256,
       source.title AS contract_source_title,
       source.url AS contract_source_url,
       source.retrieved_at AS contract_source_retrieved_at,
       source.content_sha256 AS contract_source_sha256,
       archive.attestation_sha256 AS contract_archive_attestation_sha256,
       (SELECT COUNT(*) FROM public_contract_parties party
        WHERE party.public_contract_id = contract.id) AS public_party_count,
       (SELECT COUNT(*) FROM contract_match_reviews review
        WHERE review.public_contract_id = contract.id) AS public_match_review_count,
       (SELECT COUNT(*) FROM interest_relationships relationship
        WHERE relationship.public_contract_id = contract.id) AS public_relationship_count
FROM public_contracts contract
JOIN base_public_contract_publication_snapshots publication
  ON publication.id = contract.current_publication_snapshot_id
 AND publication.public_contract_id = contract.id
JOIN source_documents source ON source.id = publication.source_document_id
JOIN LATERAL (
  SELECT attestation.attestation_sha256
  FROM source_archive_attestations attestation
  WHERE attestation.source_document_id = source.id
    AND attestation.content_sha256 = source.content_sha256
    AND attestation.retrieval_url = source.url
    AND attestation.retrieved_at = source.retrieved_at
  ORDER BY attestation.archived_at DESC, attestation.id DESC
  LIMIT 1
) archive ON TRUE
WHERE contract.id = $1
  AND contract.publication_status::text = 'PUBLISHED'
  AND contract.verification_status::text = 'VERIFIED'
  AND source.publisher::text = 'BASE_GOV'
  AND source.kind::text = 'OPEN_DATASET'
  AND source.url ~ '^https://'
"""


_MATCH_SQL = """
WITH active_organisations AS (
  SELECT organisation.id,
         organisation_publication.id AS publication_snapshot_id,
         organisation_publication.identity_observation_id,
         organisation_publication.source_document_id,
         organisation_publication.legal_name,
         organisation_publication.kind,
         organisation_publication.registry_record_id,
         organisation_publication.official_url,
         organisation_publication.source_record_sha256,
         organisation_publication.publication_proof_sha256,
         identity.protected_identifier_digest,
         organisation_source.title AS source_title,
         organisation_source.url AS source_url,
         organisation_source.retrieved_at AS source_retrieved_at,
         organisation_source.content_sha256 AS source_sha256,
         organisation_archive.attestation_sha256 AS archive_attestation_sha256,
         COUNT(*) OVER (
           PARTITION BY identity.protected_identifier_digest
         ) AS exact_organisation_count
  FROM base_public_organisation_publication_snapshots organisation_publication
  JOIN organisations organisation
    ON organisation.id = organisation_publication.organisation_id
   AND organisation.current_publication_snapshot_id = organisation_publication.id
  JOIN base_organisation_identity_observations identity
    ON identity.id = organisation_publication.identity_observation_id
  JOIN source_documents organisation_source
    ON organisation_source.id = organisation_publication.source_document_id
  JOIN LATERAL (
    SELECT attestation.attestation_sha256
    FROM source_archive_attestations attestation
    WHERE attestation.source_document_id = organisation_source.id
      AND attestation.content_sha256 = organisation_source.content_sha256
      AND attestation.retrieval_url = organisation_source.url
      AND attestation.retrieved_at = organisation_source.retrieved_at
    ORDER BY attestation.archived_at DESC, attestation.id DESC
    LIMIT 1
  ) organisation_archive ON TRUE
  WHERE identity.identifier_scheme = 'PORTUGUESE_FISCAL_IDENTIFIER'
    AND identity.identity_scope = 'ORGANISATION_IDENTITY_ONLY'
    AND identity.link_status = 'UNLINKED_PRIVATE'
    AND identity.publication_eligible = FALSE
    AND organisation.publication_status::text = 'PUBLISHED'
    AND organisation.verification_status::text = 'VERIFIED'
    AND organisation_source.publisher::text = 'JUSTICE_REGISTRY'
    AND organisation_source.kind::text = 'ORGANISATION_REGISTRY'
    AND organisation_source.url ~ '^https://'
)
SELECT $1::text AS public_contract_id,
       $2::text AS contract_publication_snapshot_id,
       party.id AS contract_party_snapshot_id,
       party.ordinal AS contract_party_ordinal,
       party.role::text AS contract_party_role,
       party.source_name AS contract_party_source_name,
       active_organisation.id AS organisation_id,
       active_organisation.publication_snapshot_id AS organisation_publication_snapshot_id,
       active_organisation.identity_observation_id AS organisation_identity_observation_id,
       active_organisation.legal_name AS organisation_legal_name,
       active_organisation.kind::text AS organisation_kind,
       active_organisation.registry_record_id,
       active_organisation.official_url AS organisation_official_url,
       $3::text AS contract_source_document_id,
       active_organisation.source_document_id AS organisation_source_document_id,
       $4::char(64) AS contract_source_record_sha256,
       active_organisation.source_record_sha256 AS organisation_source_record_sha256,
       $5::char(64) AS contract_publication_proof_sha256,
       active_organisation.publication_proof_sha256 AS organisation_publication_proof_sha256,
       $6::text AS contract_source_title,
       $7::text AS contract_source_url,
       $8::timestamp AS contract_source_retrieved_at,
       $9::char(64) AS contract_source_sha256,
       $10::char(64) AS contract_archive_attestation_sha256,
       active_organisation.source_title AS organisation_source_title,
       active_organisation.source_url AS organisation_source_url,
       active_organisation.source_retrieved_at AS organisation_source_retrieved_at,
       active_organisation.source_sha256 AS organisation_source_sha256,
       active_organisation.archive_attestation_sha256 AS organisation_archive_attestation_sha256,
       active_organisation.exact_organisation_count,
       candidate.id AS existing_candidate_id,
       candidate.decision::text AS existing_candidate_decision,
       candidate.created_by_alias AS existing_candidate_created_by_alias,
       candidate.created_at AS existing_candidate_created_at
FROM base_contract_party_snapshots party
JOIN active_organisations active_organisation
  ON active_organisation.protected_identifier_digest = party.protected_identifier_digest
LEFT JOIN base_contract_organisation_match_candidates candidate
  ON candidate.contract_publication_snapshot_id = $2
 AND candidate.contract_party_snapshot_id = party.id
 AND candidate.organisation_publication_snapshot_id = active_organisation.publication_snapshot_id
WHERE party.contract_snapshot_id = $11
  AND party.protected_identifier_digest IS NOT NULL
  AND party.protected_identifier_digest ~ '^[0-9a-f]{64}$'
  AND active_organisation.source_document_id <> $3
  AND ($12::text IS NULL OR party.id = $12)
  AND ($13::text IS NULL OR active_organisation.id = $13)
ORDER BY party.ordinal, active_organisation.legal_name, active_organisation.id
"""


class BaseContractOrganisationMatchRepository:
    """Cria somente a fila privada; a decisão e o grafo têm portas posteriores."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    @staticmethod
    def _require_staff(actor: StaffSession) -> None:
        if actor.assurance_level != "aal2" or actor.role not in (
            StaffRole.ADMIN,
            StaffRole.REVIEWER,
        ):
            raise EditorialConflictError("A proposta exige autenticação multifator")

    @staticmethod
    async def _contract(connection: asyncpg.Connection, public_contract_id: str) -> dict[str, Any]:
        row = await connection.fetchrow(_CONTRACT_SQL, public_contract_id)
        if row is None:
            raise EditorialNotFoundError("Contrato BASE publicado e ativo não encontrado")
        result = dict(row)
        _identifier(result["public_contract_id"], pattern=_PUBLIC_CONTRACT_ID, label="O contrato")
        _identifier(
            result["contract_publication_snapshot_id"],
            pattern=_CONTRACT_PUBLICATION_ID,
            label="A publicação contratual",
        )
        result["contract_source_url"] = _official_url(
            result["contract_source_url"], publisher="BASE_GOV"
        )
        result["contract_object"] = _safe_text(
            result["contract_object"], label="objeto_do_contrato", maximum=10000
        )
        result["official_contract_id"] = _safe_text(
            result["official_contract_id"], label="referencia_do_contrato", maximum=200
        )
        return result

    @staticmethod
    async def _rows(
        connection: asyncpg.Connection,
        contract: Mapping[str, Any],
        *,
        contract_party_snapshot_id: str | None = None,
        organisation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        records = await connection.fetch(
            _MATCH_SQL,
            contract["public_contract_id"],
            contract["contract_publication_snapshot_id"],
            contract["contract_source_document_id"],
            contract["contract_source_record_sha256"],
            contract["contract_publication_proof_sha256"],
            contract["contract_source_title"],
            contract["contract_source_url"],
            contract["contract_source_retrieved_at"],
            contract["contract_source_sha256"],
            contract["contract_archive_attestation_sha256"],
            contract["contract_snapshot_id"],
            contract_party_snapshot_id,
            organisation_id,
        )
        return [dict(record) for record in records]

    @staticmethod
    def _present(row: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
        for field, pattern in (
            ("organisation_id", _PUBLIC_ORGANISATION_ID),
            ("organisation_publication_snapshot_id", _ORGANISATION_PUBLICATION_ID),
            ("contract_party_snapshot_id", _OPAQUE_ID),
        ):
            _identifier(row[field], pattern=pattern, label="A referência do candidato")
        if row["contract_party_role"] not in (
            "CONTRACTING_AUTHORITY",
            "CONTRACTOR",
            "CO_CONTRACTOR",
        ) or row["organisation_kind"] not in (
            "PUBLIC_BODY",
            "COMPANY",
            "NON_PROFIT",
            "EUROPEAN_BODY",
            "OTHER",
        ):
            raise EditorialSourceError("A categoria da parte ou organização deixou de ser válida")
        graph_count = sum(
            _count(contract[key], label="A contagem pública")
            for key in (
                "public_party_count",
                "public_match_review_count",
                "public_relationship_count",
            )
        )
        blockers: list[dict[str, str]] = []
        if _count(row["exact_organisation_count"], label="A contagem de organizações") != 1:
            blockers.append(
                {
                    "code": "EXACT_IDENTIFIER_NOT_UNIQUE",
                    "detail": (
                        "O identificador protegido corresponde a mais de uma publicação ativa."
                    ),
                }
            )
        if graph_count:
            blockers.append(
                {
                    "code": "PUBLIC_GRAPH_ALREADY_MATERIALISED",
                    "detail": "O contrato já contém materialização pública fora desta porta.",
                }
            )
        existing = None
        if row["existing_candidate_id"] is not None:
            existing = {
                "id": row["existing_candidate_id"],
                "decision": _exact_text(
                    row["existing_candidate_decision"],
                    expected=_PENDING_DECISION,
                    label="O estado do candidato",
                ),
                "created_by_alias": _safe_text(
                    row["existing_candidate_created_by_alias"], label="alias_editorial", maximum=80
                ),
                "created_at": _iso(row["existing_candidate_created_at"]),
            }
        return {
            "contract_publication_snapshot_id": row["contract_publication_snapshot_id"],
            "contract_party_snapshot_id": row["contract_party_snapshot_id"],
            "contract_party": {
                "ordinal": _count(row["contract_party_ordinal"], label="A posição da parte"),
                "role": row["contract_party_role"],
                "source_name": _safe_text(
                    row["contract_party_source_name"],
                    label="designacao_da_parte",
                    maximum=500,
                ),
                "protected_identifier_observed": True,
            },
            "organisation_id": row["organisation_id"],
            "organisation_publication_snapshot_id": row["organisation_publication_snapshot_id"],
            "organisation": {
                "legal_name": _safe_text(
                    row["organisation_legal_name"],
                    label="denominacao_da_organizacao",
                    maximum=300,
                ),
                "kind": row["organisation_kind"],
                "registry_record_id": _safe_text(
                    row["registry_record_id"], label="referencia_do_ato", maximum=200
                ),
                "official_url": _official_url(
                    row["organisation_official_url"], publisher="JUSTICE_REGISTRY"
                ),
            },
            "contract_source": {
                "title": _safe_text(
                    row["contract_source_title"],
                    label="titulo_da_fonte_do_contrato",
                    maximum=500,
                ),
                "url": _official_url(row["contract_source_url"], publisher="BASE_GOV"),
                "retrieved_at": _iso(row["contract_source_retrieved_at"]),
                "content_sha256": _digest(
                    row["contract_source_sha256"], label="A fonte do contrato"
                ),
                "source_record_sha256": _digest(
                    row["contract_source_record_sha256"], label="A prova do contrato"
                ),
                "archive_attestation_sha256": _digest(
                    row["contract_archive_attestation_sha256"],
                    label="O arquivo do contrato",
                ),
            },
            "organisation_source": {
                "title": _safe_text(
                    row["organisation_source_title"],
                    label="titulo_da_fonte_da_organizacao",
                    maximum=500,
                ),
                "url": _official_url(row["organisation_source_url"], publisher="JUSTICE_REGISTRY"),
                "retrieved_at": _iso(row["organisation_source_retrieved_at"]),
                "content_sha256": _digest(
                    row["organisation_source_sha256"], label="A fonte da organização"
                ),
                "source_record_sha256": _digest(
                    row["organisation_source_record_sha256"],
                    label="A prova da organização",
                ),
                "archive_attestation_sha256": _digest(
                    row["organisation_archive_attestation_sha256"],
                    label="O arquivo da organização",
                ),
            },
            "candidate_proof_sha256": _candidate_proof(row),
            "method": _EXACT_METHOD,
            "decision": "PENDING_REVIEW",
            "existing_candidate": existing,
            "eligible": not blockers and existing is None,
            "blockers": blockers,
            "protected_identifier_exposed": False,
            "name_or_fuzzy_matching_used": False,
            "public_party_created": False,
            "match_review_created": False,
            "public_relationship_created": False,
        }

    async def inspect(self, *, public_contract_id: str) -> dict[str, Any]:
        async with (
            self.pool.acquire() as connection,
            connection.transaction(isolation="repeatable_read", readonly=True),
        ):
            contract = await self._contract(connection, public_contract_id)
            rows = await self._rows(connection, contract)
            counts = await connection.fetchrow(
                """SELECT COUNT(*) AS total,
                          COUNT(protected_identifier_digest) AS protected
                   FROM base_contract_party_snapshots
                   WHERE contract_snapshot_id = $1""",
                contract["contract_snapshot_id"],
            )
        items = [self._present(row, contract) for row in rows]
        matched_parties = {
            str(row["contract_party_snapshot_id"])
            for row in rows
            if int(row["exact_organisation_count"]) == 1
        }
        return {
            "public_contract": {
                "id": contract["public_contract_id"],
                "official_contract_id": contract["official_contract_id"],
                "object": contract["contract_object"],
                "publication_snapshot_id": contract["contract_publication_snapshot_id"],
                "source": {
                    "title": _safe_text(
                        contract["contract_source_title"],
                        label="titulo_da_fonte_do_contrato",
                        maximum=500,
                    ),
                    "url": contract["contract_source_url"],
                    "retrieved_at": _iso(contract["contract_source_retrieved_at"]),
                    "content_sha256": _digest(
                        contract["contract_source_sha256"], label="A fonte do contrato"
                    ),
                },
            },
            "items": items,
            "party_count": int(counts["total"]),
            "protected_party_count": int(counts["protected"]),
            "exact_matched_party_count": len(matched_parties),
            "candidate_pair_count": len(items),
            "protected_identifier_exposed": False,
            "name_or_fuzzy_matching_used": False,
            "public_relation_created": False,
            "creation_rule": _RULE,
        }

    async def create(
        self,
        *,
        payload: BaseContractOrganisationMatchCandidateRequest,
        actor: StaffSession,
    ) -> dict[str, Any]:
        self._require_staff(actor)
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.fetchval(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    (
                        "base-contract-organisation-candidate:"
                        f"{payload.expected_contract_party_snapshot_id}:"
                        f"{payload.expected_organisation_id}"
                    ),
                )
                await connection.fetchval(
                    """SELECT pg_advisory_xact_lock(hashtextextended(
                         'base-organisation-publication:' || protected_identifier_digest, 0))
                       FROM base_contract_party_snapshots WHERE id = $1""",
                    payload.expected_contract_party_snapshot_id,
                )
                await connection.fetchval(
                    "SELECT id FROM public_contracts WHERE id = $1 FOR UPDATE",
                    payload.expected_public_contract_id,
                )
                await connection.fetchval(
                    "SELECT id FROM organisations WHERE id = $1 FOR UPDATE",
                    payload.expected_organisation_id,
                )
                contract = await self._contract(connection, payload.expected_public_contract_id)
                rows = await self._rows(
                    connection,
                    contract,
                    contract_party_snapshot_id=payload.expected_contract_party_snapshot_id,
                    organisation_id=payload.expected_organisation_id,
                )
                if len(rows) != 1 or int(rows[0]["exact_organisation_count"]) != 1:
                    raise EditorialSourceError(
                        "A correspondência oficial exata deixou de ser única ou ativa"
                    )
                row = rows[0]
                self._present(row, contract)
                if (
                    row["contract_publication_snapshot_id"]
                    != payload.expected_contract_publication_snapshot_id
                    or row["organisation_publication_snapshot_id"]
                    != payload.expected_organisation_publication_snapshot_id
                ):
                    raise EditorialConflictError(
                        "Uma publicação mudou; volte a comparar as duas fontes"
                    )
                proof = _candidate_proof(row)
                if not hmac.compare_digest(proof, payload.expected_candidate_proof_sha256):
                    raise EditorialConflictError(
                        "A prova do candidato mudou; volte a comparar as duas fontes"
                    )
                if any(
                    int(contract[key])
                    for key in (
                        "public_party_count",
                        "public_match_review_count",
                        "public_relationship_count",
                    )
                ):
                    raise EditorialConflictError(
                        "A criação foi recusada porque existe materialização pública"
                    )
                candidate_id = f"base_contract_org_candidate_{uuid.uuid4().hex}"
                inserted = await connection.fetchrow(
                    """INSERT INTO base_contract_organisation_match_candidates
                         (id,public_contract_id,contract_publication_snapshot_id,
                          contract_party_snapshot_id,organisation_id,
                          organisation_publication_snapshot_id,
                          organisation_identity_observation_id,
                          contract_source_document_id,organisation_source_document_id,
                          method,decision,contract_source_record_sha256,
                          organisation_source_record_sha256,candidate_proof_sha256,
                          rationale,created_by_id,created_by_alias)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,
                               'EXACT_PROTECTED_IDENTIFIER','PENDING_REVIEW',$10,$11,$12,
                               $13,$14,$15)
                       ON CONFLICT (contract_publication_snapshot_id,
                                    contract_party_snapshot_id,
                                    organisation_publication_snapshot_id) DO NOTHING
                       RETURNING id,created_by_alias,created_at""",
                    candidate_id,
                    row["public_contract_id"],
                    row["contract_publication_snapshot_id"],
                    row["contract_party_snapshot_id"],
                    row["organisation_id"],
                    row["organisation_publication_snapshot_id"],
                    row["organisation_identity_observation_id"],
                    row["contract_source_document_id"],
                    row["organisation_source_document_id"],
                    _digest(row["contract_source_record_sha256"], label="A prova do contrato"),
                    _digest(
                        row["organisation_source_record_sha256"],
                        label="A prova da organização",
                    ),
                    proof,
                    payload.rationale,
                    actor.staff_id,
                    actor.public_alias,
                )
                created = inserted is not None
                if not created:
                    existing = await connection.fetchrow(
                        """SELECT id,method::text,decision::text,created_by_alias,created_at
                           FROM base_contract_organisation_match_candidates
                           WHERE contract_publication_snapshot_id=$1
                             AND contract_party_snapshot_id=$2
                             AND organisation_publication_snapshot_id=$3""",
                        row["contract_publication_snapshot_id"],
                        row["contract_party_snapshot_id"],
                        row["organisation_publication_snapshot_id"],
                    )
                    if existing is None:
                        raise EditorialConflictError("O candidato não pôde ser confirmado")
                    candidate_id = str(existing["id"])
                    created_at = existing["created_at"]
                    created_by_alias = str(existing["created_by_alias"])
                else:
                    candidate_id = str(inserted["id"])
                    created_at = inserted["created_at"]
                    created_by_alias = str(inserted["created_by_alias"])
            return {
                "created": created,
                "id": candidate_id,
                "public_contract_id": row["public_contract_id"],
                "contract_party_snapshot_id": row["contract_party_snapshot_id"],
                "organisation_id": row["organisation_id"],
                "method": "EXACT_PROTECTED_IDENTIFIER",
                "decision": "PENDING_REVIEW",
                "candidate_proof_sha256": proof,
                "created_by_alias": created_by_alias,
                "created_at": _iso(created_at),
                "protected_identifier_exposed": False,
                "name_or_fuzzy_matching_used": False,
                "public_party_created": False,
                "match_review_created": False,
                "public_relationship_created": False,
                "creation_rule": _RULE,
            }
        except asyncpg.PostgresError:
            raise EditorialConflictError(
                "A base de dados recusou o candidato sem criar qualquer relação pública"
            ) from None
