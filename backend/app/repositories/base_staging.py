"""Persistência privada e append-only dos snapshots do Portal BASE.

Este módulo não escreve em tabelas públicas nem cria correspondências. É um
mixin do repositório PostgreSQL para manter o circuito BASE isolado.
"""

import hashlib
import json
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import asyncpg
from pydantic import HttpUrl

from app.core.config import Settings
from app.core.security import require_official_url
from app.models.api import BaseContractCollection
from app.models.archive import RawArchiveReceipt

BASE_STAGING_ONLY_MESSAGE = (
    "A persistência BASE só é permitida em staging, com arquivo prévio dos bytes "
    "oficiais e confirmação explícita; ingestão não constitui revisão nem publicação."
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _database_timestamp(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _utc_database_timestamp(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _millisecond_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("A atestação de arquivo exige datas com fuso horário")
    utc_value = value.astimezone(UTC)
    return utc_value.replace(microsecond=(utc_value.microsecond // 1000) * 1000)


def _archive_attestation_sha256(
    *,
    source_document_id: str,
    receipt: RawArchiveReceipt,
    archived_at: datetime,
    archived_by: str,
) -> str:
    canonical = json.dumps(
        {
            "source_document_id": source_document_id,
            "storage_backend": receipt.storage_backend,
            "storage_key": receipt.storage_key,
            "content_sha256": receipt.content_sha256,
            "byte_size": receipt.byte_size,
            "mime_type": receipt.mime_type,
            "retrieval_url": str(receipt.source_url),
            "retrieved_at": _millisecond_utc(receipt.retrieved_at).isoformat(),
            "archived_at": archived_at.isoformat(),
            "archived_by": archived_by,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _stable_base_staging_id(prefix: str, *parts: str) -> str:
    canonical = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:32]}"


def _base_utc_millisecond(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("As datas normalizadas BASE devem incluir fuso horário")
    return _millisecond_utc(value)


def _base_snapshot_sha256(
    collection: BaseContractCollection,
    *,
    persist_identifier_digests: bool,
) -> str:
    """Calcula o hash canónico da normalização sem expor identificadores.

    Datas de recolha não participam: uma repetição dos mesmos bytes com a mesma
    versão do parser deve produzir o mesmo snapshot. Quando existe pepper durável,
    o HMAC participa no hash; sem pepper, o digest efémero é deliberadamente omitido.
    """

    contracts: list[dict[str, Any]] = []
    for contract in sorted(collection.contracts, key=lambda item: item.source_id):
        payload = contract.model_dump(mode="json")
        source = payload.get("source")
        if isinstance(source, dict):
            source.pop("retrieved_at", None)
        for field_name, value in (
            ("decision_at", contract.decision_at),
            ("signed_at", contract.signed_at),
            ("published_at", contract.published_at),
        ):
            canonical_timestamp = _base_utc_millisecond(value)
            payload[field_name] = (
                canonical_timestamp.isoformat() if canonical_timestamp is not None else None
            )
        for field_name, parties in (
            ("contracting_authorities", contract.contracting_authorities),
            ("contractors", contract.contractors),
        ):
            serialised_parties: list[dict[str, Any]] = []
            for party in parties:
                party_payload = party.model_dump(mode="json")
                digest = (
                    party.protected_identifier_digest.get_secret_value()
                    if persist_identifier_digests and party.protected_identifier_digest is not None
                    else None
                )
                party_payload["protected_identifier_digest"] = digest
                serialised_parties.append(party_payload)
            payload[field_name] = serialised_parties
        contracts.append(payload)

    canonical = json.dumps(
        {
            "schema": "base-staging-v1",
            "resource": {
                "format": collection.dataset_resource.format.upper(),
                "url": str(collection.dataset_resource.url),
                "year": collection.dataset_resource.year,
            },
            "document_sha256": collection.document_sha256,
            "identifier_digests_stored": persist_identifier_digests,
            "warnings": collection.warnings,
            "contracts": contracts,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_base_staging_input(
    collection: BaseContractCollection,
    *,
    archive_receipt: RawArchiveReceipt | None,
    code_version: str,
) -> None:
    if archive_receipt is None:
        raise ValueError("A persistência BASE exige arquivo prévio dos bytes oficiais")
    if not code_version.strip() or len(code_version) > 200:
        raise ValueError("A versão do parser BASE é inválida")
    if collection.dataset_resource.year is None:
        raise ValueError("A persistência BASE exige o ano explícito do recurso")
    if not 2012 <= collection.dataset_resource.year <= datetime.now(UTC).year + 1:
        raise ValueError("O ano do recurso BASE está fora do intervalo público esperado")
    if collection.dataset_resource.format.upper() not in {"JSON", "XML", "ZIP"}:
        raise ValueError("O formato do recurso BASE não é suportado para persistência")
    if not 1 <= len(collection.dataset_resource.title.strip()) <= 500:
        raise ValueError("O título do recurso BASE é inválido")
    if not collection.contracts:
        raise ValueError(
            "A coleção BASE normalizada está vazia; os dados ficam indisponíveis e não são "
            "persistidos automaticamente"
        )
    if any(warning.startswith("Amostra limitada") for warning in collection.warnings):
        raise ValueError("Uma amostra BASE limitada não pode ser persistida como snapshot anual")
    if collection.collected_at.tzinfo is None:
        raise ValueError("A data de recolha BASE deve incluir fuso horário")

    dataset_url = require_official_url(str(collection.dataset_resource.url))
    if archive_receipt.content_sha256 != collection.document_sha256:
        raise ValueError("O recibo de arquivo não corresponde ao hash do recurso BASE")
    if str(archive_receipt.source_url) != dataset_url:
        raise ValueError("O recibo de arquivo não corresponde ao URL efetivo do recurso BASE")
    if archive_receipt.retrieved_at.astimezone(UTC) != collection.collected_at.astimezone(UTC):
        raise ValueError("O recibo de arquivo não corresponde à data de recolha BASE")

    source_ids: set[str] = set()
    for contract in collection.contracts:
        if (
            not contract.source_id.strip()
            or contract.source_id != contract.source_id.strip()
            or len(contract.source_id) > 500
        ):
            raise ValueError("Um identificador oficial BASE é vazio ou não está normalizado")
        if contract.source_id in source_ids:
            raise ValueError("A coleção BASE contém identificadores oficiais duplicados")
        source_ids.add(contract.source_id)
        if not contract.object.strip():
            raise ValueError("O objeto de um contrato BASE está vazio")
        if contract.source.publisher.value != "BASE":
            raise ValueError("Um contrato não está ligado ao editor oficial BASE")
        if str(contract.source.url) != dataset_url:
            raise ValueError("Um contrato não está ligado ao URL efetivo do dump BASE")
        if contract.source.content_sha256 != collection.document_sha256:
            raise ValueError("Um contrato não está ligado ao SHA-256 do dump BASE")
        if contract.source.retrieved_at.tzinfo is None:
            raise ValueError("A data da fonte de um contrato BASE deve incluir fuso horário")
        if contract.source.retrieved_at.astimezone(UTC) != collection.collected_at.astimezone(UTC):
            raise ValueError("Um contrato não está ligado à data de recolha do dump BASE")
        if contract.direct_official_url is not None:
            require_official_url(str(contract.direct_official_url))
        if not re.fullmatch(r"[A-Z]{3}", contract.currency):
            raise ValueError("A moeda de um contrato BASE é inválida")
        if contract.base_value is not None and (
            not _fits_decimal_20_2(contract.base_value) or contract.base_value < 0
        ):
            raise ValueError("O valor base de um contrato BASE excede o formato decimal seguro")
        if contract.contract_value is not None and (
            not _fits_decimal_20_2(contract.contract_value) or contract.contract_value < 0
        ):
            raise ValueError("O valor de um contrato BASE excede o formato decimal seguro")
        if contract.execution_days is not None and not (
            0 <= contract.execution_days <= 2_147_483_647
        ):
            raise ValueError("O prazo de um contrato BASE excede o intervalo seguro")
        _base_utc_millisecond(contract.decision_at)
        _base_utc_millisecond(contract.signed_at)
        _base_utc_millisecond(contract.published_at)

        for party in contract.contracting_authorities:
            if party.role.value != "CONTRACTING_AUTHORITY":
                raise ValueError("Uma entidade adjudicante BASE tem um papel incoerente")
        for party in contract.contractors:
            if party.role.value not in {"CONTRACTOR", "CO_CONTRACTOR"}:
                raise ValueError("Um adjudicatário BASE tem um papel incoerente")


def _base_contract_rows(
    collection: BaseContractCollection,
    *,
    batch_id: str,
) -> Iterator[tuple[Any, ...]]:
    for contract in collection.contracts:
        contract_id = _stable_base_staging_id("base_contract", batch_id, contract.source_id)
        yield (
            contract_id,
            batch_id,
            contract.source_id,
            contract.object,
            contract.procedure.value,
            contract.cpv_code,
            contract.base_value,
            contract.contract_value,
            contract.currency,
            _database_timestamp(_base_utc_millisecond(contract.decision_at)),
            _database_timestamp(_base_utc_millisecond(contract.signed_at)),
            _database_timestamp(_base_utc_millisecond(contract.published_at)),
            contract.execution_days,
            str(contract.direct_official_url) if contract.direct_official_url else None,
        )


def _base_party_rows(
    collection: BaseContractCollection,
    *,
    batch_id: str,
    persist_identifier_digests: bool,
) -> Iterator[tuple[Any, ...]]:
    for contract in collection.contracts:
        contract_id = _stable_base_staging_id("base_contract", batch_id, contract.source_id)
        parties = [*contract.contracting_authorities, *contract.contractors]
        for ordinal, party in enumerate(parties):
            digest = (
                party.protected_identifier_digest.get_secret_value()
                if persist_identifier_digests and party.protected_identifier_digest is not None
                else None
            )
            yield (
                _stable_base_staging_id("base_party", contract_id, str(ordinal)),
                contract_id,
                ordinal,
                party.role.value,
                party.name,
                digest,
            )


def _fits_decimal_20_2(value: Decimal) -> bool:
    if not value.is_finite():
        return False
    normalised = value.normalize()
    digits = normalised.as_tuple().digits
    exponent = normalised.as_tuple().exponent
    if not isinstance(exponent, int):
        return False
    scale = max(-exponent, 0)
    integer_digits = max(len(digits) + exponent, 0)
    return scale <= 2 and integer_digits <= 18


class BaseStagingRepositoryMixin:
    settings: Settings
    pool: asyncpg.Pool | None

    async def _start_sync_run(
        self,
        *,
        source_name: str,
        dataset_url: str,
        code_version: str,
    ) -> str:
        raise NotImplementedError

    async def _finish_sync_run(
        self,
        sync_id: str,
        *,
        status_value: str,
        records_read: int,
        records_written: int,
        warnings: list[str],
        error_message: str | None = None,
    ) -> None:
        raise NotImplementedError

    @staticmethod
    async def _ensure_source_document(
        connection: asyncpg.Connection,
        *,
        publisher: str,
        kind: str,
        title: str,
        url: str,
        retrieved_at: datetime,
        content_sha256: str,
        mime_type: str | None,
        parser_version: str,
    ) -> str:
        raise NotImplementedError

    @staticmethod
    async def _attest_source_archive(
        connection: asyncpg.Connection,
        *,
        source_document_id: str,
        receipt: RawArchiveReceipt,
        archived_by: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def store_base_collection(
        self,
        collection: BaseContractCollection,
        *,
        code_version: str,
        archive_receipt: RawArchiveReceipt | None = None,
    ) -> dict[str, int]:
        """Acrescenta um snapshot BASE privado; nunca cria entidades públicas.

        A validação do recibo e da coerência da coleção ocorre antes de qualquer
        acesso à base. Os contratos e partes são carregados por COPY para tabelas
        próprias, protegidas por triggers append-only.
        """

        if self.settings.environment not in {"test", "staging"}:
            raise RuntimeError(BASE_STAGING_ONLY_MESSAGE)
        _validate_base_staging_input(
            collection,
            archive_receipt=archive_receipt,
            code_version=code_version,
        )
        assert archive_receipt is not None
        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")

        persist_identifier_digests = self.settings.protected_identifier_pepper is not None
        identifier_digest_count = sum(
            party.protected_identifier_digest is not None
            for contract in collection.contracts
            for party in [*contract.contracting_authorities, *contract.contractors]
        )
        party_count = sum(
            len(contract.contracting_authorities) + len(contract.contractors)
            for contract in collection.contracts
        )
        normalised_sha256 = _base_snapshot_sha256(
            collection,
            persist_identifier_digests=persist_identifier_digests,
        )
        warnings = list(collection.warnings)
        if identifier_digest_count and not persist_identifier_digests:
            warnings.append(
                "Dados indisponíveis para cruzamento fiscal: PROTECTED_IDENTIFIER_PEPPER "
                "não configurado; nenhum digest efémero foi persistido"
            )

        records_read = len(collection.contracts)
        sync_id = await self._start_sync_run(
            source_name="BASE_GOV",
            dataset_url=str(collection.dataset_resource.url),
            code_version=code_version,
        )
        contracts_written = 0
        parties_written = 0
        batch_created = False
        archive_attestation: dict[str, Any] = {"created": False}
        try:
            async with self.pool.acquire() as connection, connection.transaction():
                source_document_id = await self._ensure_source_document(
                    connection,
                    publisher="BASE_GOV",
                    kind="OPEN_DATASET",
                    title=(f"Portal BASE — contratos — {collection.dataset_resource.year}"),
                    url=str(collection.dataset_resource.url),
                    retrieved_at=collection.collected_at,
                    content_sha256=collection.document_sha256,
                    mime_type=archive_receipt.mime_type,
                    parser_version=code_version,
                )
                archive_attestation = await self._attest_source_archive(
                    connection,
                    source_document_id=source_document_id,
                    receipt=archive_receipt,
                    archived_by=f"sync:{code_version}",
                )
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    f"base:{source_document_id}:{code_version}",
                )

                batch_id = _stable_base_staging_id(
                    "base_batch",
                    source_document_id,
                    code_version,
                )
                batch = await connection.fetchrow(
                    """
                    INSERT INTO base_staging_batches
                        (id, source_document_id, sync_run_id, resource_year,
                         resource_title, resource_format, parser_version,
                         normalised_sha256, identifier_digests_stored,
                         contract_count, party_count, collected_at, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
                    ON CONFLICT (source_document_id, parser_version) DO NOTHING
                    RETURNING id
                    """,
                    batch_id,
                    source_document_id,
                    sync_id,
                    collection.dataset_resource.year,
                    collection.dataset_resource.title,
                    collection.dataset_resource.format.upper(),
                    code_version,
                    normalised_sha256,
                    persist_identifier_digests,
                    records_read,
                    party_count,
                    _database_timestamp(_millisecond_utc(collection.collected_at)),
                )
                batch_created = batch is not None
                if not batch_created:
                    existing = await connection.fetchrow(
                        """
                        SELECT id, resource_year, resource_title, resource_format,
                               normalised_sha256, identifier_digests_stored,
                               contract_count, party_count, collected_at
                        FROM base_staging_batches
                        WHERE source_document_id = $1 AND parser_version = $2
                        """,
                        source_document_id,
                        code_version,
                    )
                    if existing is None:
                        raise RuntimeError("O lote BASE não foi criado nem encontrado")
                    expected_existing = {
                        "resource_year": collection.dataset_resource.year,
                        "resource_format": collection.dataset_resource.format.upper(),
                        "normalised_sha256": normalised_sha256,
                        "identifier_digests_stored": persist_identifier_digests,
                        "contract_count": records_read,
                        "party_count": party_count,
                    }
                    observed_existing = {key: existing[key] for key in expected_existing}
                    if observed_existing != expected_existing:
                        raise ValueError(
                            "O lote BASE existente diverge da normalização atual; é necessária "
                            "uma nova versão do parser"
                        )
                    batch_id = str(existing["id"])
                else:
                    await connection.copy_records_to_table(
                        "base_contract_snapshots",
                        records=_base_contract_rows(collection, batch_id=batch_id),
                        columns=(
                            "id",
                            "batch_id",
                            "source_id",
                            "object",
                            "procedure",
                            "cpv_code",
                            "base_value",
                            "contract_value",
                            "currency",
                            "decision_at",
                            "signed_at",
                            "published_at",
                            "execution_days",
                            "direct_official_url",
                        ),
                    )
                    await connection.copy_records_to_table(
                        "base_contract_party_snapshots",
                        records=_base_party_rows(
                            collection,
                            batch_id=batch_id,
                            persist_identifier_digests=persist_identifier_digests,
                        ),
                        columns=(
                            "id",
                            "contract_snapshot_id",
                            "ordinal",
                            "role",
                            "source_name",
                            "protected_identifier_digest",
                        ),
                    )
                    contracts_written = records_read
                    parties_written = party_count
                    await connection.execute(
                        """
                        INSERT INTO audit_events
                            (id, entity_type, entity_id, action, actor_alias,
                             before_json, after_json, reason, created_at)
                        VALUES ($1, 'BASE_STAGING_BATCH', $2,
                                'INGESTED_OFFICIAL_SNAPSHOT', $3, NULL, $4::jsonb,
                                'Snapshot BASE privado; sem revisão ou publicação', NOW())
                        """,
                        _new_id("audit"),
                        batch_id,
                        f"sync:{code_version}",
                        json.dumps(
                            {
                                "source_document_id": source_document_id,
                                "archive_attestation_id": archive_attestation["id"],
                                "resource_year": collection.dataset_resource.year,
                                "normalised_sha256": normalised_sha256,
                                "contract_count": records_read,
                                "party_count": party_count,
                                "identifier_digests_stored": persist_identifier_digests,
                                "publication_eligible": False,
                            },
                            ensure_ascii=False,
                        ),
                    )

            await self._finish_sync_run(
                sync_id,
                status_value="PARTIAL" if warnings else "SUCCEEDED",
                records_read=records_read,
                records_written=contracts_written + parties_written,
                warnings=warnings,
            )
        except Exception:
            await self._finish_sync_run(
                sync_id,
                status_value="FAILED",
                records_read=records_read,
                records_written=0,
                warnings=warnings,
                error_message=(
                    "Persistência BASE interrompida; nenhuma mensagem de dados privados foi "
                    "guardada no SyncRun"
                ),
            )
            raise

        return {
            "records_read": records_read,
            "records_written": contracts_written + parties_written,
            "contracts_written": contracts_written,
            "parties_written": parties_written,
            "batch_created": int(batch_created),
            "archive_attestations_written": int(archive_attestation["created"]),
            "identifier_digests_written": (
                identifier_digest_count if batch_created and persist_identifier_digests else 0
            ),
        }

    async def inspect_base_staging(self, *, year: int) -> dict[str, Any]:
        """Inspeciona metadados e contagens BASE sem devolver nomes ou HMAC."""

        if self.pool is None:
            raise RuntimeError("Base de dados não configurada")
        if year < 2012 or year > 2100:
            raise ValueError("Ano BASE inválido para inspeção")

        async with self.pool.acquire() as connection:
            snapshot = await connection.fetchrow(
                """
                SELECT batch.id AS batch_id, batch.resource_year,
                       batch.resource_title, batch.resource_format,
                       batch.parser_version, batch.normalised_sha256,
                       batch.identifier_digests_stored, batch.contract_count,
                       batch.party_count, batch.collected_at, batch.created_at,
                       run.id AS sync_run_id, run.status::text AS sync_status,
                       run.started_at, run.finished_at, run.records_read,
                       run.records_written, run.warnings, run.error_message,
                       run.code_version,
                       source.id AS source_document_id,
                       source.publisher::text AS source_publisher,
                       source.kind::text AS source_kind, source.title AS source_title,
                       source.url AS source_url, source.retrieved_at,
                       source.content_sha256, source.mime_type,
                       archive.id AS archive_attestation_id,
                       archive.storage_backend, archive.storage_key,
                       archive.content_sha256 AS archive_content_sha256,
                       archive.byte_size, archive.mime_type AS archive_mime_type,
                       archive.retrieval_url, archive.retrieved_at AS archive_retrieved_at,
                       archive.archived_at, archive.archived_by,
                       archive.attestation_sha256,
                       (SELECT COUNT(*) FROM base_contract_snapshots contract
                        WHERE contract.batch_id = batch.id) AS observed_contract_count,
                       (SELECT COUNT(*)
                        FROM base_contract_party_snapshots party
                        JOIN base_contract_snapshots contract
                          ON contract.id = party.contract_snapshot_id
                        WHERE contract.batch_id = batch.id) AS observed_party_count,
                       (SELECT COUNT(*)
                        FROM base_contract_party_snapshots party
                        JOIN base_contract_snapshots contract
                          ON contract.id = party.contract_snapshot_id
                        WHERE contract.batch_id = batch.id
                          AND party.protected_identifier_digest IS NOT NULL)
                           AS protected_identifier_digest_count
                FROM base_staging_batches batch
                JOIN sync_runs run ON run.id = batch.sync_run_id
                JOIN source_documents source ON source.id = batch.source_document_id
                LEFT JOIN LATERAL (
                    SELECT candidate.*
                    FROM source_archive_attestations candidate
                    WHERE candidate.source_document_id = source.id
                    ORDER BY candidate.archived_at DESC, candidate.id DESC
                    LIMIT 1
                ) archive ON TRUE
                WHERE batch.resource_year = $1
                  AND run.status IN ('SUCCEEDED', 'PARTIAL')
                  AND run.finished_at IS NOT NULL
                ORDER BY batch.collected_at DESC, batch.id DESC
                LIMIT 1
                """,
                year,
            )
            if snapshot is None:
                raise ValueError(
                    f"Não existe snapshot BASE persistido e concluído para {year}; "
                    "dados indisponíveis"
                )
            distribution_rows = await connection.fetch(
                """
                SELECT dimension, value, count
                FROM (
                    SELECT 'procedure'::text AS dimension,
                           contract.procedure::text AS value,
                           COUNT(*)::bigint AS count
                    FROM base_contract_snapshots contract
                    WHERE contract.batch_id = $1
                    GROUP BY contract.procedure
                    UNION ALL
                    SELECT 'role'::text AS dimension, party.role::text AS value,
                           COUNT(*)::bigint AS count
                    FROM base_contract_party_snapshots party
                    JOIN base_contract_snapshots contract
                      ON contract.id = party.contract_snapshot_id
                    WHERE contract.batch_id = $1
                    GROUP BY party.role
                ) distribution
                ORDER BY dimension, value
                """,
                str(snapshot["batch_id"]),
            )

        warnings: Any = snapshot["warnings"]
        if isinstance(warnings, str):
            try:
                warnings = json.loads(warnings)
            except json.JSONDecodeError:
                warnings = [warnings]
        elif warnings is None:
            warnings = []
        elif not isinstance(warnings, list):
            warnings = [warnings]

        procedures: dict[str, int] = {}
        roles: dict[str, int] = {}
        for row in distribution_rows:
            target = procedures if row["dimension"] == "procedure" else roles
            target[str(row["value"])] = int(row["count"])

        source_url = require_official_url(str(snapshot["source_url"]))
        source_sha256 = str(snapshot["content_sha256"])
        archive_present = snapshot["archive_attestation_id"] is not None
        expected_archive_key = f"sha256/{source_sha256[:2]}/{source_sha256}"
        observed_contract_count = int(snapshot["observed_contract_count"])
        observed_party_count = int(snapshot["observed_party_count"])
        stored_contract_count = int(snapshot["contract_count"])
        stored_party_count = int(snapshot["party_count"])
        identifiers_stored = bool(snapshot["identifier_digests_stored"])
        attestation_hash_matches = False
        if archive_present:
            archived_receipt = RawArchiveReceipt(
                storage_backend=str(snapshot["storage_backend"]),
                storage_key=str(snapshot["storage_key"]),
                content_sha256=str(snapshot["archive_content_sha256"]),
                byte_size=int(snapshot["byte_size"]),
                mime_type=snapshot["archive_mime_type"],
                source_url=HttpUrl(source_url),
                retrieved_at=_utc_database_timestamp(snapshot["archive_retrieved_at"]),
                recorded_at=_utc_database_timestamp(snapshot["archived_at"]),
                object_created=False,
            )
            expected_attestation_sha256 = _archive_attestation_sha256(
                source_document_id=str(snapshot["source_document_id"]),
                receipt=archived_receipt,
                archived_at=_millisecond_utc(_utc_database_timestamp(snapshot["archived_at"])),
                archived_by=str(snapshot["archived_by"]),
            )
            attestation_hash_matches = expected_attestation_sha256 == str(
                snapshot["attestation_sha256"]
            )

        return {
            "year": year,
            "publication_eligible": False,
            "publication_rule": (
                "Inspeção privada de staging: não cria correspondências, revisão humana, "
                "entidades públicas ou publicação."
            ),
            "batch": {
                "id": str(snapshot["batch_id"]),
                "resource_title": str(snapshot["resource_title"]),
                "resource_format": str(snapshot["resource_format"]),
                "parser_version": str(snapshot["parser_version"]),
                "normalised_sha256": str(snapshot["normalised_sha256"]),
                "collected_at": snapshot["collected_at"],
                "created_at": snapshot["created_at"],
            },
            "sync_run": {
                "id": str(snapshot["sync_run_id"]),
                "status": str(snapshot["sync_status"]),
                "started_at": snapshot["started_at"],
                "finished_at": snapshot["finished_at"],
                "records_read": int(snapshot["records_read"]),
                "records_written": int(snapshot["records_written"]),
                "warnings": warnings,
                "error_message": snapshot["error_message"],
                "code_version": str(snapshot["code_version"]),
            },
            "provenance": {
                "source_document_id": str(snapshot["source_document_id"]),
                "publisher": str(snapshot["source_publisher"]),
                "kind": str(snapshot["source_kind"]),
                "title": str(snapshot["source_title"]),
                "url": source_url,
                "retrieved_at": snapshot["retrieved_at"],
                "content_sha256": source_sha256,
                "mime_type": snapshot["mime_type"],
                "archive_attestation": (
                    {
                        "id": str(snapshot["archive_attestation_id"]),
                        "storage_backend": str(snapshot["storage_backend"]),
                        "storage_key": str(snapshot["storage_key"]),
                        "content_sha256": str(snapshot["archive_content_sha256"]),
                        "byte_size": int(snapshot["byte_size"]),
                        "mime_type": snapshot["archive_mime_type"],
                        "retrieval_url": str(snapshot["retrieval_url"]),
                        "retrieved_at": snapshot["archive_retrieved_at"],
                        "archived_at": snapshot["archived_at"],
                        "archived_by": str(snapshot["archived_by"]),
                        "attestation_sha256": str(snapshot["attestation_sha256"]),
                    }
                    if archive_present
                    else None
                ),
            },
            "counts": {
                "contracts": observed_contract_count,
                "parties": observed_party_count,
                "protected_identifier_digests": int(snapshot["protected_identifier_digest_count"]),
            },
            "distributions": {"procedures": procedures, "roles": roles},
            "protected_identifier_matching": {
                "status": "AVAILABLE" if identifiers_stored else "UNAVAILABLE",
                "description": (
                    "Estão disponíveis apenas HMAC-SHA-256 produzidos com pepper durável."
                    if identifiers_stored
                    else "Dados indisponíveis: o lote não persistiu digests sem pepper durável."
                ),
            },
            "checks": {
                "official_source_url": bool(source_url),
                "valid_source_sha256": bool(re.fullmatch(r"[0-9a-f]{64}", source_sha256)),
                "valid_normalised_sha256": bool(
                    re.fullmatch(r"[0-9a-f]{64}", str(snapshot["normalised_sha256"]))
                ),
                "sync_finished": snapshot["finished_at"] is not None,
                "sync_status_allows_inspection": snapshot["sync_status"]
                in {"SUCCEEDED", "PARTIAL"},
                "parser_matches_sync_code_version": (
                    snapshot["parser_version"] == snapshot["code_version"]
                ),
                "contract_count_matches_batch": (observed_contract_count == stored_contract_count),
                "party_count_matches_batch": observed_party_count == stored_party_count,
                "procedure_distribution_matches_contracts": (
                    sum(procedures.values()) == observed_contract_count
                ),
                "role_distribution_matches_parties": (sum(roles.values()) == observed_party_count),
                "archive_attested": archive_present,
                "archive_hash_matches_source": (
                    archive_present and snapshot["archive_content_sha256"] == source_sha256
                ),
                "archive_url_matches_source": (
                    archive_present and snapshot["retrieval_url"] == source_url
                ),
                "archive_key_matches_source_hash": (
                    archive_present and snapshot["storage_key"] == expected_archive_key
                ),
                "attestation_hash_valid": attestation_hash_matches,
            },
        }
