import hashlib
import io
import json
import re
import secrets
import unicodedata
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

import ijson
from dateutil.parser import parse as parse_datetime
from defusedxml import ElementTree as SafeElementTree
from pydantic import HttpUrl

from app.core.config import Settings
from app.core.security import (
    hmac_protected_identifier,
    is_official_url,
    normalise_public_name,
)
from app.models.api import (
    BaseContractCollection,
    BaseDatasetResource,
    ContractMatchCandidate,
    ContractMatchMethod,
    ContractPartyRole,
    OfficialSource,
    PublicActorMatchKey,
    PublicContractParty,
    PublicContractProcedure,
    PublicContractRecord,
    SourcePublisher,
)
from app.services.http import OfficialHttpClient
from app.services.public_interest import assess_public_actor, association_has_public_evidence


def _normalise_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normalise_public_name(value))


def _field(record: dict[str, Any], *aliases: str) -> Any | None:
    index = {_normalise_key(str(key)): value for key, value in record.items()}
    for alias in aliases:
        candidate = index.get(_normalise_key(alias))
        if candidate not in (None, "", []):
            return candidate
    return None


def _as_text(value: Any | None) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def _parse_date(value: Any | None) -> datetime | None:
    text = _as_text(value)
    if not text:
        return None
    try:
        parsed = cast(datetime, parse_datetime(text, dayfirst=True))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (OverflowError, ValueError):
        return None


def _parse_decimal(value: Any | None) -> Decimal | None:
    text = _as_text(value)
    if not text:
        return None
    cleaned = re.sub(r"[^0-9,.-]", "", text)
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        parsed = Decimal(cleaned)
        return parsed if parsed >= 0 else None
    except InvalidOperation:
        return None


def _parse_int(value: Any | None) -> int | None:
    text = _as_text(value)
    if not text:
        return None
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None


_PRIVATE_IDENTIFIER_SEQUENCE = re.compile(r"(?<!\d)\d(?:[\W_]*\d){8}(?!\d)")
_STRICT_PARTY_WITH_IDENTIFIER = re.compile(
    r"(?P<identifier>[0-9]{9}) - (?P<name>.+)",
)


class _UnsafeFiscalIdentifierError(ValueError):
    """Impede que um identificador fiscal potencial atravesse um campo publicável."""


def _contains_private_identifier(value: str) -> bool:
    return _PRIVATE_IDENTIFIER_SEQUENCE.search(value) is not None


def _canonical_identifier(value: Any | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        raise _UnsafeFiscalIdentifierError
    text = _as_text(value)
    if not text:
        return None
    digits = "".join(
        str(unicodedata.decimal(character)) for character in text if character.isdecimal()
    )
    if len(digits) != 9:
        raise _UnsafeFiscalIdentifierError
    return digits


class BaseGovCollector:
    """Lê os dumps abertos do Portal BASE sem raspar os resultados de pesquisa.

    O caminho normal usa o catálogo do dados.gov.pt. Uma API de grande volume do
    IMPIC pode ser configurada separadamente quando a organização tiver a autorização
    exigida; o coletor não tenta contornar esse controlo.
    """

    def __init__(self, settings: Settings, http: OfficialHttpClient) -> None:
        self.settings = settings
        self.http = http
        configured_pepper = (
            settings.protected_identifier_pepper.get_secret_value()
            if settings.protected_identifier_pepper is not None
            else None
        )
        # Sem segredo configurado, um pepper efémero conserva a deduplicação dentro
        # desta recolha sem reter o identificador em claro nem permitir cruzamentos.
        self._identifier_pepper = configured_pepper or secrets.token_hex(32)

    def _protected_identifier_digest(self, value: Any | None) -> str | None:
        identifier = _canonical_identifier(value)
        if identifier is None:
            return None
        return hmac_protected_identifier(identifier, self._identifier_pepper)

    async def discover_resource(self, year: int) -> BaseDatasetResource:
        if self.settings.base_resource_url is not None:
            configured_url = str(self.settings.base_resource_url)
            return BaseDatasetResource(
                title=f"Recurso BASE configurado para {year}",
                format=self._format_from_name(configured_url),
                url=HttpUrl(configured_url),
                year=year,
            )

        response = await self.http.get(str(self.settings.base_dataset_catalog_url))
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise ValueError("O catálogo oficial do dados.gov.pt não devolveu JSON válido") from exc

        resources = payload.get("resources", []) if isinstance(payload, dict) else []
        candidates: list[BaseDatasetResource] = []
        for raw in resources:
            if not isinstance(raw, dict):
                continue
            title = _as_text(raw.get("title") or raw.get("name")) or "Recurso BASE"
            url = _as_text(raw.get("url") or raw.get("latest") or raw.get("resource_url"))
            declared_format = _as_text(raw.get("format")) or self._format_from_name(url or title)
            if not url or not is_official_url(url):
                continue
            resource_year = self._year_from_text(f"{title} {url}")
            if resource_year == year and declared_format.upper() in {"JSON", "XML", "ZIP"}:
                candidates.append(
                    BaseDatasetResource(
                        title=title,
                        format=declared_format.upper(),
                        url=HttpUrl(url),
                        year=resource_year,
                    )
                )
        if not candidates:
            raise LookupError(f"Recurso aberto de contratos BASE para {year} não encontrado")
        return candidates[-1]

    async def collect(self, year: int, *, limit: int | None = None) -> BaseContractCollection:
        if year < 2012 or year > datetime.now(UTC).year + 1:
            raise ValueError("Ano BASE fora do intervalo público esperado")
        resource = await self.discover_resource(year)
        response = await self.http.get(
            str(resource.url),
            max_bytes=self.settings.base_max_bytes,
        )
        collected_at = datetime.now(UTC)
        digest = hashlib.sha256(response.content).hexdigest()
        effective_resource = resource.model_copy(
            update={"url": HttpUrl(str(response.url))},
        )
        contracts_by_source_id: dict[str, PublicContractRecord] = {}
        comparison_keys_by_source_id: dict[
            str,
            tuple[str, tuple[str | None, ...], tuple[str | None, ...]],
        ] = {}
        equivalent_duplicates_by_source_id: dict[str, int] = {}
        conflicting_source_ids: set[str] = set()
        unsafe_source_ids: set[str] = set()
        warnings: list[str] = []
        skipped = 0
        unsafe_identifier_rows = 0
        normalised = 0
        for raw in self.iter_records(response.content, resource.format):
            try:
                contract = self.normalise_contract(
                    raw,
                    dataset_url=str(response.url),
                    document_sha256=digest,
                    retrieved_at=collected_at,
                )
            except _UnsafeFiscalIdentifierError:
                unsafe_identifier_rows += 1
                unsafe_source_id = _as_text(
                    _field(raw, "idcontrato", "id_contrato", "contractId", "contratoId", "id")
                )
                if unsafe_source_id:
                    unsafe_source_ids.add(unsafe_source_id)
                    contracts_by_source_id.pop(unsafe_source_id, None)
                    comparison_keys_by_source_id.pop(unsafe_source_id, None)
                    equivalent_duplicates_by_source_id.pop(unsafe_source_id, None)
                continue
            if contract is None:
                skipped += 1
                continue
            normalised += 1
            source_id = contract.source_id
            if source_id not in conflicting_source_ids and source_id not in unsafe_source_ids:
                comparison_key = self._contract_comparison_key(contract)
                previous_comparison_key = comparison_keys_by_source_id.get(source_id)
                if previous_comparison_key is None:
                    contracts_by_source_id[source_id] = contract
                    comparison_keys_by_source_id[source_id] = comparison_key
                elif previous_comparison_key == comparison_key:
                    equivalent_duplicates_by_source_id[source_id] = (
                        equivalent_duplicates_by_source_id.get(source_id, 0) + 1
                    )
                else:
                    # Não é seguro eleger uma das versões como verdadeira. O ID
                    # inteiro fica fora da coleção até revisão da fonte.
                    contracts_by_source_id.pop(source_id, None)
                    comparison_keys_by_source_id.pop(source_id, None)
                    equivalent_duplicates_by_source_id.pop(source_id, None)
                    conflicting_source_ids.add(source_id)
            if limit is not None and normalised >= limit:
                warnings.append(f"Amostra limitada aos primeiros {limit} contratos normalizados")
                break
        contracts = list(contracts_by_source_id.values())
        equivalent_duplicates = sum(equivalent_duplicates_by_source_id.values())
        if equivalent_duplicates:
            if equivalent_duplicates == 1:
                warnings.append("1 linha duplicada equivalente foi conservada apenas uma vez")
            else:
                warnings.append(
                    f"{equivalent_duplicates} linhas duplicadas equivalentes foram "
                    "conservadas apenas uma vez"
                )
        if conflicting_source_ids:
            conflict_count = len(conflicting_source_ids)
            if conflict_count == 1:
                warnings.append(
                    "1 identificador de contrato apresentou conteúdo normalizado conflitante; "
                    "todas as versões desse identificador foram excluídas e requerem revisão"
                )
            else:
                warnings.append(
                    f"{conflict_count} identificadores de contrato apresentaram conteúdo "
                    "normalizado conflitante; todas as versões desses identificadores foram "
                    "excluídas e requerem revisão"
                )
        if unsafe_identifier_rows:
            if unsafe_identifier_rows == 1:
                warnings.append(
                    "1 linha continha um identificador fiscal potencial num campo textual "
                    "publicável; o contrato foi excluído e requer revisão"
                )
            else:
                warnings.append(
                    f"{unsafe_identifier_rows} linhas continham identificadores fiscais "
                    "potenciais em campos textuais publicáveis; os contratos foram excluídos "
                    "e requerem revisão"
                )
        if skipped:
            warnings.append(f"{skipped} linhas sem identificador foram ignoradas")
        without_direct_link = sum(contract.direct_official_url is None for contract in contracts)
        if without_direct_link:
            warnings.append(
                f"{without_direct_link} linhas não continham ligação direta; "
                "conservou-se o dump oficial"
            )
        return BaseContractCollection(
            dataset_resource=effective_resource,
            document_sha256=digest,
            contracts=contracts,
            warnings=warnings,
            collected_at=collected_at,
        )

    @staticmethod
    def _contract_comparison_key(
        contract: PublicContractRecord,
    ) -> tuple[str, tuple[str | None, ...], tuple[str | None, ...]]:
        """Compara todo o conteúdo normalizado sem criar um digest desprotegido de NIF/NIPC."""

        payload = contract.model_dump(
            mode="json",
            exclude={"source": {"retrieved_at"}},
        )
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        public_fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        # O digest protegido tem ``exclude=True`` no modelo público. A
        # igualdade exata ainda tem de participar na decisão de deduplicação,
        # mas só durante esta recolha em memória. O identificador em claro é
        # convertido imediatamente para HMAC-SHA-256 com pepper e não entra na coleção.
        authority_identifiers = tuple(
            party.protected_identifier_digest.get_secret_value()
            if party.protected_identifier_digest is not None
            else None
            for party in contract.contracting_authorities
        )
        contractor_identifiers = tuple(
            party.protected_identifier_digest.get_secret_value()
            if party.protected_identifier_digest is not None
            else None
            for party in contract.contractors
        )
        return public_fingerprint, authority_identifiers, contractor_identifiers

    def iter_records(self, content: bytes, declared_format: str) -> Iterator[dict[str, Any]]:
        format_name = declared_format.upper()
        if format_name == "ZIP" or content.startswith(b"PK\x03\x04"):
            yield from self._iter_zip(content)
            return
        if format_name == "XML" or content.lstrip().startswith(b"<"):
            yield from self._iter_xml(content)
            return
        yield from self._iter_json(content)

    def _iter_zip(self, content: bytes) -> Iterator[dict[str, Any]]:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            files = [item for item in archive.infolist() if not item.is_dir()]
            if len(files) > 20:
                raise ValueError("Arquivo BASE contém demasiados ficheiros")
            total_size = sum(item.file_size for item in files)
            if total_size > self.settings.base_max_uncompressed_bytes:
                raise ValueError("Arquivo BASE excede o limite descomprimido configurado")
            supported = [
                item for item in files if item.filename.casefold().endswith((".json", ".xml"))
            ]
            if not supported:
                raise ValueError("Arquivo BASE não contém JSON ou XML")
            for item in supported:
                if item.compress_size and item.file_size / item.compress_size > 250:
                    raise ValueError("Taxa de compressão BASE excede o limite de segurança")
                with archive.open(item) as handle:
                    if item.filename.casefold().endswith(".xml"):
                        yield from self._iter_xml(handle.read())
                    else:
                        yield from self._iter_json_stream(handle)

    def _iter_json(self, content: bytes) -> Iterator[dict[str, Any]]:
        yield from self._iter_json_stream(io.BytesIO(content))

    @staticmethod
    def _iter_json_stream(handle: Any) -> Iterator[dict[str, Any]]:
        start = handle.read(512)
        handle.seek(0)
        first = start.lstrip()[:1]
        if first == b"[":
            for item in ijson.items(handle, "item"):
                if isinstance(item, dict):
                    yield item
            return
        if first != b"{":
            raise ValueError("Recurso BASE não contém JSON reconhecível")
        for prefix in ("contratos.item", "contracts.item", "data.item", "results.item"):
            handle.seek(0)
            found = False
            for item in ijson.items(handle, prefix):
                if isinstance(item, dict):
                    found = True
                    yield item
            if found:
                return
        raise ValueError("Estrutura do objeto JSON BASE não reconhecida")

    @staticmethod
    def _iter_xml(content: bytes) -> Iterator[dict[str, Any]]:
        for _event, element in SafeElementTree.iterparse(io.BytesIO(content), events=("end",)):
            local_tag = str(element.tag).rsplit("}", 1)[-1].casefold()
            if local_tag not in {"contrato", "contract"}:
                continue
            record: dict[str, Any] = {}
            for child in list(element):
                key = str(child.tag).rsplit("}", 1)[-1]
                record[key] = (child.text or "").strip()
            element.clear()
            if record:
                yield record

    def normalise_contract(
        self,
        record: dict[str, Any],
        *,
        dataset_url: str,
        document_sha256: str,
        retrieved_at: datetime | None = None,
    ) -> PublicContractRecord | None:
        source_id = _as_text(
            _field(record, "idcontrato", "id_contrato", "contractId", "contratoId", "id")
        )
        if not source_id:
            return None
        object_text = (
            _as_text(
                _field(
                    record,
                    "objectoContrato",
                    "objetoContrato",
                    "objecto",
                    "objeto",
                    "descricao",
                    "object",
                )
            )
            or "Objeto não indicado na linha da fonte"
        )
        if _contains_private_identifier(object_text):
            raise _UnsafeFiscalIdentifierError
        procedure_text = _as_text(
            _field(record, "tipoProcedimento", "procedimento", "procedureType", "procedure")
        )
        direct_url_text = _as_text(
            _field(record, "urlContrato", "linkContrato", "urlDetalhe", "officialUrl", "url")
        )
        direct_url = (
            direct_url_text
            if direct_url_text
            and is_official_url(direct_url_text)
            and not _contains_private_identifier(direct_url_text)
            else None
        )
        source = OfficialSource(
            publisher=SourcePublisher.BASE_GOV,
            label="Portal BASE — dump oficial de contratos",
            url=HttpUrl(dataset_url),
            retrieved_at=retrieved_at or datetime.now(UTC),
            content_sha256=document_sha256,
        )
        authorities = self._parties(
            _field(
                record,
                "entidadeAdjudicante",
                "entidadesAdjudicantes",
                "adjudicante",
                "contractingAuthority",
            ),
            ContractPartyRole.CONTRACTING_AUTHORITY,
        )
        contractors = self._parties(
            _field(
                record,
                "adjudicatario",
                "adjudicatarios",
                "entidadeAdjudicataria",
                "contractors",
                "supplier",
            ),
            ContractPartyRole.CONTRACTOR,
        )
        return PublicContractRecord(
            source_id=source_id,
            object=object_text,
            procedure=self._procedure(procedure_text),
            cpv_code=_as_text(_field(record, "cpv", "codigoCPV", "cpvCode")),
            base_value=_parse_decimal(_field(record, "precoBase", "valorBase", "basePrice")),
            contract_value=_parse_decimal(
                _field(record, "precoContratual", "valorContrato", "contractValue", "price")
            ),
            decision_at=_parse_date(
                _field(record, "dataDecisaoAdjudicacao", "dataAdjudicacao", "awardDate")
            ),
            signed_at=_parse_date(
                _field(record, "dataCelebracaoContrato", "dataContrato", "signedAt")
            ),
            published_at=_parse_date(
                _field(record, "dataPublicacao", "dataPublicacaoPortal", "publishedAt")
            ),
            execution_days=_parse_int(
                _field(record, "prazoExecucao", "prazoExecucaoDias", "executionDays")
            ),
            contracting_authorities=authorities,
            contractors=contractors,
            source=source,
            direct_official_url=HttpUrl(direct_url) if direct_url else None,
        )

    def _parties(
        self,
        value: Any | None,
        role: ContractPartyRole,
    ) -> list[PublicContractParty]:
        if value is None:
            return []
        if isinstance(value, list):
            result: list[PublicContractParty] = []
            for item in value:
                result.extend(self._parties(item, role))
            return result
        if isinstance(value, dict):
            name = _as_text(_field(value, "nome", "designacao", "denominacao", "name", "entidade"))
            if not name:
                return []
            if _contains_private_identifier(name):
                raise _UnsafeFiscalIdentifierError
            return [
                PublicContractParty(
                    name=name,
                    protected_identifier_digest=self._protected_identifier_digest(
                        _field(value, "nif", "nipc", "numeroFiscal", "taxId")
                    ),
                    role=role,
                )
            ]
        text = _as_text(value)
        if not text:
            return []
        parties: list[PublicContractParty] = []
        for raw_party in re.split(r"\s*[;|]\s*", text):
            party_text = raw_party.strip()
            if not party_text:
                continue
            strict_match = _STRICT_PARTY_WITH_IDENTIFIER.fullmatch(party_text)
            if strict_match is not None:
                name = strict_match.group("name")
                if _contains_private_identifier(name):
                    raise _UnsafeFiscalIdentifierError
                parties.append(
                    PublicContractParty(
                        name=name,
                        protected_identifier_digest=self._protected_identifier_digest(
                            strict_match.group("identifier")
                        ),
                        role=role,
                    )
                )
                continue
            if _contains_private_identifier(party_text):
                raise _UnsafeFiscalIdentifierError
            parties.append(PublicContractParty(name=party_text, role=role))
        return parties

    @staticmethod
    def _procedure(value: str | None) -> PublicContractProcedure:
        key = normalise_public_name(value or "")
        if "ajuste direto" in key:
            return PublicContractProcedure.DIRECT_AWARD
        if "consulta previa" in key:
            return PublicContractProcedure.PRIOR_CONSULTATION
        if "concurso publico" in key:
            return PublicContractProcedure.PUBLIC_TENDER
        if "concurso limitado" in key:
            return PublicContractProcedure.LIMITED_TENDER
        if "negociacao" in key:
            return PublicContractProcedure.NEGOTIATED_PROCEDURE
        if "acordo quadro" in key:
            return PublicContractProcedure.FRAMEWORK_AGREEMENT
        return PublicContractProcedure.OTHER if key else PublicContractProcedure.UNKNOWN

    @staticmethod
    def _year_from_text(value: str) -> int | None:
        # Os recursos oficiais usam nomes como ``contratos2026.zip``. Uma
        # fronteira de palavra não reconhece o ano quando este vem logo depois
        # de letras e pode acabar por escolher o ano geral do catálogo
        # ``contratos-de-2012-a-2026``. Limitamos apenas por algarismos para
        # aceitar o nome do ficheiro sem confundir timestamps como 20260802.
        matches = re.findall(r"(?<!\d)(20\d{2})(?!\d)", value)
        return int(matches[-1]) if matches else None

    @staticmethod
    def _format_from_name(value: str) -> str:
        lowered = value.casefold().split("?", 1)[0]
        if lowered.endswith(".xml"):
            return "XML"
        if lowered.endswith(".json"):
            return "JSON"
        return "ZIP" if lowered.endswith(".zip") else "JSON"


class ContractMatcher:
    """Produz candidatos de correspondência, nunca conclusões públicas."""

    def __init__(self, *, pepper: str | None) -> None:
        self.protected_identifiers_enabled = pepper is not None

    def match(
        self,
        contracts: list[PublicContractRecord],
        actors: list[PublicActorMatchKey],
    ) -> list[ContractMatchCandidate]:
        eligible = [actor for actor in actors if assess_public_actor(actor).allowed]
        name_index: dict[str, list[PublicActorMatchKey]] = {}
        protected_index: dict[str, list[PublicActorMatchKey]] = {}
        association_id_index: dict[
            str,
            list[tuple[PublicActorMatchKey, HttpUrl]],
        ] = {}
        association_name_index: dict[
            str,
            list[tuple[PublicActorMatchKey, HttpUrl]],
        ] = {}
        for eligible_actor in eligible:
            name_index.setdefault(
                normalise_public_name(eligible_actor.public_name),
                [],
            ).append(eligible_actor)
            if (
                self.protected_identifiers_enabled
                and eligible_actor.protected_nif_digest is not None
            ):
                digest = eligible_actor.protected_nif_digest.get_secret_value()
                protected_index.setdefault(digest, []).append(eligible_actor)
            for actor_association in eligible_actor.official_associations:
                evidence = str(actor_association.official_evidence_url)
                if not association_has_public_evidence(evidence):
                    continue
                if (
                    self.protected_identifiers_enabled
                    and actor_association.protected_nipc_digest is not None
                ):
                    digest = actor_association.protected_nipc_digest.get_secret_value()
                    association_id_index.setdefault(digest, []).append(
                        (eligible_actor, actor_association.official_evidence_url)
                    )
                association_name_index.setdefault(
                    normalise_public_name(actor_association.organisation_name),
                    [],
                ).append((eligible_actor, actor_association.official_evidence_url))

        matches: dict[tuple[str, str, str, str, str, str], ContractMatchCandidate] = {}
        for contract in contracts:
            contract_source_sha256 = contract.source.content_sha256
            if contract_source_sha256 is None or not re.fullmatch(
                r"[0-9a-f]{64}", contract_source_sha256
            ):
                raise ValueError("O candidato BASE exige o SHA-256 válido do dump descarregado")
            parties = [*contract.contracting_authorities, *contract.contractors]
            for party in parties:
                candidate_matches: list[
                    tuple[
                        PublicActorMatchKey,
                        ContractMatchMethod,
                        Decimal,
                        HttpUrl | None,
                    ]
                ] = []
                protected_digest = (
                    party.protected_identifier_digest.get_secret_value()
                    if party.protected_identifier_digest is not None
                    else None
                )
                if protected_digest and self.protected_identifiers_enabled:
                    candidate_matches = [
                        (
                            actor,
                            ContractMatchMethod.EXACT_PROTECTED_IDENTIFIER,
                            Decimal("1.0000"),
                            None,
                        )
                        for actor in protected_index.get(protected_digest, [])
                    ]
                if (
                    not candidate_matches
                    and protected_digest
                    and self.protected_identifiers_enabled
                ):
                    candidate_matches = [
                        (
                            actor,
                            ContractMatchMethod.EXACT_PUBLIC_ORGANISATION_ID,
                            Decimal("1.0000"),
                            evidence,
                        )
                        for actor, evidence in association_id_index.get(
                            protected_digest,
                            [],
                        )
                    ]
                normalised_party = normalise_public_name(party.name)
                if not candidate_matches:
                    candidate_matches = [
                        (
                            actor,
                            ContractMatchMethod.NORMALISED_NAME,
                            Decimal("0.9500"),
                            evidence,
                        )
                        for actor, evidence in association_name_index.get(normalised_party, [])
                    ]
                if not candidate_matches:
                    candidate_matches = [
                        (
                            actor,
                            ContractMatchMethod.NORMALISED_NAME,
                            Decimal("0.9000"),
                            None,
                        )
                        for actor in name_index.get(normalised_party, [])
                    ]
                for matched_actor, method, score, association_evidence in candidate_matches:
                    candidate = ContractMatchCandidate(
                        contract_source_id=contract.source_id,
                        person_id=matched_actor.person_id,
                        public_name=matched_actor.public_name,
                        matched_party_name=party.name,
                        party_role=party.role,
                        method=method,
                        score=score,
                        contract_source_url=contract.source.url,
                        contract_source_sha256=contract_source_sha256,
                        contract_source_retrieved_at=contract.source.retrieved_at,
                        contract_direct_official_url=contract.direct_official_url,
                        actor_source_url=matched_actor.official_role_source_url,
                        association_evidence_url=association_evidence,
                    )
                    key = (
                        contract.source_id,
                        matched_actor.person_id,
                        party.name,
                        method.value,
                        party.role.value,
                        str(association_evidence or ""),
                    )
                    matches[key] = candidate
        return list(matches.values())
