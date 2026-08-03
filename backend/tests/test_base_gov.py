import asyncio
import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import hmac_protected_identifier
from app.models.api import BaseContractCollection, PublicActorMatchKey
from app.services.base_gov import BaseGovCollector, ContractMatcher

FIXTURES = Path(__file__).parent / "fixtures"
TEST_PEPPER = "pepper-de-teste-com-pelo-menos-32-carateres"


class NoNetworkHttp:
    pass


class CatalogueResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def json(self) -> object:
        return self.payload


class CatalogueHttp:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    async def get(self, _url: str) -> CatalogueResponse:
        return CatalogueResponse(self.payload)


class DatasetResponse:
    def __init__(self, payload: list[dict[str, object]], url: str) -> None:
        self.content = json.dumps(payload).encode("utf-8")
        self.url = url


class DatasetHttp:
    def __init__(
        self,
        payload: list[dict[str, object]],
        *,
        response_url: str = "https://dados.gov.pt/datasets/contratos2026.json",
    ) -> None:
        self.payload = payload
        self.response_url = response_url

    async def get(self, _url: str, **_kwargs: object) -> DatasetResponse:
        return DatasetResponse(self.payload, self.response_url)


def collector(*, pepper: str | None = None) -> BaseGovCollector:
    return BaseGovCollector(
        Settings(environment="test", protected_identifier_pepper=pepper),
        NoNetworkHttp(),  # type: ignore[arg-type]
    )


def collect_records(payload: list[dict[str, object]]) -> BaseContractCollection:
    settings = Settings(
        environment="test",
        base_resource_url="https://dados.gov.pt/datasets/contratos2026.json",
    )
    base = BaseGovCollector(settings, DatasetHttp(payload))  # type: ignore[arg-type]
    return asyncio.run(base.collect(2026))


def test_normalises_base_json_and_keeps_direct_official_source() -> None:
    payload = (FIXTURES / "base_contracts.json").read_bytes()
    rows = list(collector().iter_records(payload, "JSON"))
    contract = collector().normalise_contract(
        rows[0],
        dataset_url="https://dados.gov.pt/api/1/datasets/r/recurso",
        document_sha256="a" * 64,
    )
    assert contract is not None
    protected_digest = contract.contractors[0].protected_identifier_digest
    assert protected_digest is not None
    assert len(protected_digest.get_secret_value()) == 64
    assert protected_digest.get_secret_value() != "123456789"
    assert contract.source_id == "BASE-DEMO-001"
    assert contract.contract_value == Decimal("110500.00")
    assert contract.procedure.value == "PUBLIC_TENDER"
    assert str(contract.source.url) == "https://dados.gov.pt/api/1/datasets/r/recurso"
    assert contract.source.content_sha256 == "a" * 64
    assert str(contract.direct_official_url).startswith("https://www.base.gov.pt/")
    assert "protected_identifier_digest" not in contract.model_dump(mode="json")["contractors"][0]


def test_xml_adapter_uses_same_normalisation_contract() -> None:
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <contratos><contrato><idContrato>X-2</idContrato>
    <objetoContrato>Obra demonstrativa</objetoContrato>
    <precoContratual>1000,50</precoContratual></contrato></contratos>"""
    rows = list(collector().iter_records(xml, "XML"))
    assert rows == [
        {
            "idContrato": "X-2",
            "objetoContrato": "Obra demonstrativa",
            "precoContratual": "1000,50",
        }
    ]


def test_matches_protected_identifier_without_exporting_it() -> None:
    raw = json.loads((FIXTURES / "base_contracts.json").read_text(encoding="utf-8"))
    raw[0]["adjudicatarios"][0]["NIF"] = "123 456 789"
    contract = collector(pepper=TEST_PEPPER).normalise_contract(
        raw[0],
        dataset_url="https://dados.gov.pt/api/1/datasets/r/recurso",
        document_sha256="b" * 64,
    )
    assert contract is not None
    protected_digest = contract.contractors[0].protected_identifier_digest
    assert protected_digest is not None
    assert protected_digest.get_secret_value() == hmac_protected_identifier(
        "123456789", TEST_PEPPER
    )
    actor = PublicActorMatchKey.model_validate(
        {
            "person_id": "person-demo",
            "public_name": "Pessoa Pública Demonstrativa",
            "public_role": "DEPUTY",
            "official_role_source_url": (
                "https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx"
            ),
            "protected_nif_digest": hmac_protected_identifier("123456789", TEST_PEPPER),
        }
    )
    matches = ContractMatcher(pepper=TEST_PEPPER).match(
        [contract],
        [actor],
    )
    assert "protected_nif_digest" not in actor.model_dump(mode="json")
    assert len(matches) == 1
    assert matches[0].method.value == "EXACT_PROTECTED_IDENTIFIER"
    exported = json.dumps(matches[0].model_dump(mode="json"))
    assert "123456789" not in exported
    assert "123 456 789" not in exported
    assert matches[0].decision == "PENDING_REVIEW"


def test_hmac_canonicalises_unicode_decimal_digits() -> None:
    assert hmac_protected_identifier("１２３４５６７８９", TEST_PEPPER) == (
        hmac_protected_identifier("123456789", TEST_PEPPER)
    )


def test_same_normalised_name_keeps_all_candidates_private_for_review() -> None:
    raw = json.loads((FIXTURES / "base_contracts.json").read_text(encoding="utf-8"))
    contract = collector(pepper=TEST_PEPPER).normalise_contract(
        raw[0],
        dataset_url="https://dados.gov.pt/api/1/datasets/r/recurso",
        document_sha256="b" * 64,
    )
    assert contract is not None
    actors = [
        PublicActorMatchKey.model_validate(
            {
                "person_id": person_id,
                "public_name": public_name,
                "public_role": "DEPUTY",
                "official_role_source_url": (
                    "https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx"
                ),
            }
        )
        for person_id, public_name in (
            ("person-name-1", "Pessoa Pública Demonstrativa"),
            ("person-name-2", "Pessoa Publica Demonstrativa"),
        )
    ]

    matches = ContractMatcher(pepper=None).match([contract], actors)

    assert {match.person_id for match in matches} == {"person-name-1", "person-name-2"}
    assert all(match.method.value == "NORMALISED_NAME" for match in matches)
    assert all(match.decision == "PENDING_REVIEW" for match in matches)


def test_parses_real_party_format_privately_and_keeps_hmac_matching() -> None:
    contract = collector(pepper=TEST_PEPPER).normalise_contract(
        {
            "idContrato": "BASE-REAL-001",
            "objetoContrato": "Aquisição de serviços",
            "adjudicatario": "123456789 - Pessoa Pública Demonstrativa",
        },
        dataset_url="https://dados.gov.pt/api/1/datasets/r/recurso",
        document_sha256="c" * 64,
    )
    assert contract is not None
    assert contract.contractors[0].name == "Pessoa Pública Demonstrativa"
    protected_digest = contract.contractors[0].protected_identifier_digest
    assert protected_digest is not None
    assert protected_digest.get_secret_value() == hmac_protected_identifier(
        "123456789", TEST_PEPPER
    )
    exported_contract = json.dumps(contract.model_dump(mode="json"))
    assert "123456789" not in exported_contract
    assert "123456789" not in repr(contract)

    actor = PublicActorMatchKey.model_validate(
        {
            "person_id": "person-real-format",
            "public_name": "Outro nome público",
            "public_role": "DEPUTY",
            "official_role_source_url": (
                "https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx"
            ),
            "protected_nif_digest": hmac_protected_identifier("123456789", TEST_PEPPER),
        }
    )
    matches = ContractMatcher(pepper=TEST_PEPPER).match(
        [contract],
        [actor],
    )

    assert len(matches) == 1
    assert matches[0].method.value == "EXACT_PROTECTED_IDENTIFIER"
    assert "123456789" not in json.dumps(matches[0].model_dump(mode="json"))


def test_discovers_year_from_resource_filename_not_catalogue_range() -> None:
    catalogue = {
        "resources": [
            {
                "title": "contratos2026.zip",
                "format": "zip",
                "url": (
                    "https://dados.gov.pt/s/resources/"
                    "contratos-publicos-portal-base-impic-contratos-de-2012-a-2026/"
                    "20260802-092811-1cae53a0/contratos2026.zip"
                ),
            },
            {
                "title": "contratos2012.zip",
                "format": "zip",
                "url": (
                    "https://dados.gov.pt/s/resources/"
                    "contratos-publicos-portal-base-impic-contratos-de-2012-a-2026/"
                    "20260802-092919-141d24f3/contratos2012.zip"
                ),
            },
        ]
    }
    http = CatalogueHttp(catalogue)
    base = BaseGovCollector(Settings(environment="test"), http)  # type: ignore[arg-type]

    resource = asyncio.run(base.discover_resource(2026))

    assert resource.title == "contratos2026.zip"
    assert resource.year == 2026
    assert str(resource.url).endswith("/contratos2026.zip")


def test_collect_keeps_one_equivalent_duplicate_without_exporting_identifier() -> None:
    first: dict[str, object] = {
        "idContrato": "BASE-DUP-001",
        "objetoContrato": "Aquisição de serviços",
        "adjudicatario": "123456789 - Empresa Demonstrativa",
    }
    second: dict[str, object] = {
        "id_contrato": " BASE-DUP-001 ",
        "objetoContrato": " Aquisição   de serviços ",
        "adjudicatario": " 123456789   -   Empresa  Demonstrativa ",
    }

    collection = collect_records([first, second])

    assert len(collection.contracts) == 1
    assert any("duplicada equivalente" in warning for warning in collection.warnings)
    exported = json.dumps(collection.model_dump(mode="json"))
    assert "123456789" not in exported


def test_collect_excludes_all_versions_when_private_identifier_conflicts() -> None:
    common: dict[str, object] = {
        "idContrato": "BASE-CONFLICT-001",
        "objetoContrato": "Aquisição de serviços",
    }
    first = {
        **common,
        "adjudicatario": "123456789 - Empresa Demonstrativa",
    }
    second = {
        **common,
        "adjudicatario": "987654321 - Empresa Demonstrativa",
    }

    collection = collect_records([first, second])

    assert collection.contracts == []
    assert any("conteúdo normalizado conflitante" in warning for warning in collection.warnings)
    exported = json.dumps(collection.model_dump(mode="json"))
    assert "123456789" not in exported
    assert "987654321" not in exported


def test_collect_quarantines_unrecognised_identifier_format_without_echoing_it() -> None:
    safe_version: dict[str, object] = {
        "idContrato": "BASE-UNSAFE-001",
        "objetoContrato": "Aquisição de serviços",
        "adjudicatario": "Empresa Demonstrativa",
    }
    unsafe_version: dict[str, object] = {
        **safe_version,
        "adjudicatario": "Empresa Demonstrativa 123456789",
    }

    collection = collect_records([safe_version, unsafe_version])

    assert collection.contracts == []
    warning_text = " ".join(collection.warnings)
    assert "campo textual publicável" in warning_text
    assert "123456789" not in warning_text
    assert "123456789" not in json.dumps(collection.model_dump(mode="json"))


@pytest.mark.parametrize(
    "unsafe_party",
    [
        "Empresa Demonstrativa 123 456 789",
        "Empresa Demonstrativa 123.456.789",
        "Empresa Demonstrativa 123,456,789",
        "Empresa Demonstrativa 123–456–789",
        "Empresa Demonstrativa 123_456_789",
        "Empresa Demonstrativa １２３４５６７８９",
        "123 456 789 - Empresa Demonstrativa",
    ],
)
def test_collect_quarantines_formatted_identifiers_in_party_names(
    unsafe_party: str,
) -> None:
    collection = collect_records(
        [
            {
                "idContrato": "BASE-FORMATTED-001",
                "objetoContrato": "Aquisição de serviços",
                "adjudicatario": unsafe_party,
            }
        ]
    )

    assert collection.contracts == []
    exported = json.dumps(collection.model_dump(mode="json"))
    assert unsafe_party not in exported
    assert "campo textual publicável" in " ".join(collection.warnings)


def test_collect_quarantines_identifiers_in_public_object_text() -> None:
    collection = collect_records(
        [
            {
                "idContrato": "BASE-OBJECT-001",
                "objetoContrato": "Serviço associado ao identificador 123 456 789",
                "adjudicatario": "Empresa Demonstrativa",
            }
        ]
    )

    assert collection.contracts == []
    exported = json.dumps(collection.model_dump(mode="json"))
    assert "123 456 789" not in exported
    assert "campo textual publicável" in " ".join(collection.warnings)


def test_collect_quarantines_nonempty_malformed_explicit_identifier() -> None:
    common: dict[str, object] = {
        "idContrato": "BASE-MALFORMED-001",
        "objetoContrato": "Aquisição de serviços",
        "adjudicatario": {
            "nome": "Empresa Demonstrativa",
        },
    }
    first = {
        **common,
        "adjudicatario": {"nome": "Empresa Demonstrativa", "nif": "12345678"},
    }
    second = {
        **common,
        "adjudicatario": {"nome": "Empresa Demonstrativa", "nif": "87654321"},
    }

    collection = collect_records([first, second])

    assert collection.contracts == []
    assert "campos textuais publicáveis" in " ".join(collection.warnings)
    exported = json.dumps(collection.model_dump(mode="json"))
    assert "12345678" not in exported
    assert "87654321" not in exported
    assert "duplicada equivalente" not in " ".join(collection.warnings)


@pytest.mark.parametrize(
    "unsafe_identifier",
    ["SEM NIF", {"valor": "123456789"}, ["123456789"]],
)
def test_collect_quarantines_nonempty_unstructured_fiscal_field(
    unsafe_identifier: object,
) -> None:
    collection = collect_records(
        [
            {
                "idContrato": "BASE-UNSTRUCTURED-001",
                "objetoContrato": "Aquisição de serviços",
                "adjudicatario": {
                    "nome": "Empresa Demonstrativa",
                    "nif": unsafe_identifier,
                },
            }
        ]
    )

    assert collection.contracts == []
    assert "campo textual publicável" in " ".join(collection.warnings)


def test_collection_provenance_uses_effective_response_url_after_redirect() -> None:
    requested_url = "https://dados.gov.pt/datasets/latest/contratos2026.json"
    effective_url = "https://dados.gov.pt/datasets/versioned/contratos2026.json"
    settings = Settings(environment="test", base_resource_url=requested_url)
    http = DatasetHttp(
        [
            {
                "idContrato": "BASE-REDIRECT-001",
                "objetoContrato": "Aquisição de serviços",
            }
        ],
        response_url=effective_url,
    )

    collection = asyncio.run(
        BaseGovCollector(settings, http).collect(2026)  # type: ignore[arg-type]
    )

    assert str(collection.dataset_resource.url) == effective_url
    assert str(collection.contracts[0].source.url) == effective_url
    assert collection.contracts[0].source.retrieved_at == collection.collected_at


def test_identifier_candidates_require_hmac_and_preserve_roles_and_hashed_source() -> None:
    contract = collector(pepper=TEST_PEPPER).normalise_contract(
        {
            "idContrato": "BASE-ROLE-001",
            "objetoContrato": "Aquisição de serviços",
            "entidadeAdjudicante": "123456789 - Empresa Igual",
            "adjudicatario": "123456789 - Empresa Igual",
            "urlContrato": "https://www.base.gov.pt/Base4/pt/detalhe/?type=contratos&id=1",
        },
        dataset_url="https://dados.gov.pt/datasets/versioned/contratos2026.json",
        document_sha256="d" * 64,
    )
    assert contract is not None
    actor = PublicActorMatchKey.model_validate(
        {
            "person_id": "person-association",
            "public_name": "Pessoa Pública",
            "public_role": "DEPUTY",
            "official_role_source_url": "https://www.parlamento.pt/",
            "official_associations": [
                {
                    "organisation_name": "Outra designação oficial",
                    "protected_nipc_digest": hmac_protected_identifier("123456789", TEST_PEPPER),
                    "official_evidence_url": "https://diariodarepublica.pt/",
                },
                {
                    "organisation_name": "Outra designação oficial",
                    "protected_nipc_digest": hmac_protected_identifier("123456789", TEST_PEPPER),
                    "official_evidence_url": "https://www.tcontas.pt/",
                },
            ],
        }
    )

    assert ContractMatcher(pepper=None).match([contract], [actor]) == []
    actor_dump = actor.model_dump(mode="json")
    assert "protected_nif_digest" not in actor_dump
    assert "protected_nipc_digest" not in actor_dump["official_associations"][0]
    matches = ContractMatcher(pepper=TEST_PEPPER).match([contract], [actor])

    assert len(matches) == 4
    assert {match.party_role.value for match in matches} == {
        "CONTRACTING_AUTHORITY",
        "CONTRACTOR",
    }
    assert all(match.method.value == "EXACT_PUBLIC_ORGANISATION_ID" for match in matches)
    assert all(
        str(match.contract_source_url)
        == "https://dados.gov.pt/datasets/versioned/contratos2026.json"
        for match in matches
    )
    assert all(match.contract_source_sha256 == "d" * 64 for match in matches)
    assert all(match.contract_direct_official_url is not None for match in matches)
    assert {str(match.association_evidence_url) for match in matches} == {
        "https://diariodarepublica.pt/",
        "https://www.tcontas.pt/",
    }
    exported = json.dumps([match.model_dump(mode="json") for match in matches])
    assert "123456789" not in exported
    assert hmac_protected_identifier("123456789", TEST_PEPPER) not in exported


def test_actor_input_rejects_plaintext_fiscal_identifiers() -> None:
    with pytest.raises(ValidationError) as error:
        PublicActorMatchKey.model_validate(
            {
                "person_id": "person-plaintext",
                "public_name": "Pessoa Pública",
                "public_role": "DEPUTY",
                "official_role_source_url": "https://www.parlamento.pt/",
                "protected_nif": "123456789",
            }
        )

    assert "123456789" not in str(error.value)


def test_actor_public_name_rejects_identifier_without_echoing_it() -> None:
    payload = {
        "person_id": "person-safe",
        "public_name": "Pessoa Pública",
        "public_role": "DEPUTY",
        "official_role_source_url": "https://www.parlamento.pt/",
    }
    payload["public_name"] = "Pessoa 987,654,321"

    with pytest.raises(ValidationError) as error:
        PublicActorMatchKey.model_validate(payload)

    assert "987,654,321" not in str(error.value)


def test_actor_person_id_accepts_uuid_without_treating_it_as_fiscal() -> None:
    actor = PublicActorMatchKey.model_validate(
        {
            "person_id": "12345678-9abc-4def-8abc-123456789abc",
            "public_name": "Pessoa Pública",
            "public_role": "DEPUTY",
            "official_role_source_url": "https://www.parlamento.pt/",
        }
    )

    assert actor.person_id == "12345678-9abc-4def-8abc-123456789abc"


def test_actor_person_id_rejects_plain_numeric_identifier_without_echoing_it() -> None:
    with pytest.raises(ValidationError) as error:
        PublicActorMatchKey.model_validate(
            {
                "person_id": "987654321",
                "public_name": "Pessoa Pública",
                "public_role": "DEPUTY",
                "official_role_source_url": "https://www.parlamento.pt/",
            }
        )

    assert "987654321" not in str(error.value)


def test_actor_association_name_rejects_identifier_without_echoing_it() -> None:
    with pytest.raises(ValidationError) as error:
        PublicActorMatchKey.model_validate(
            {
                "person_id": "person-safe",
                "public_name": "Pessoa Pública",
                "public_role": "DEPUTY",
                "official_role_source_url": "https://www.parlamento.pt/",
                "official_associations": [
                    {
                        "organisation_name": "Empresa 987–654–321",
                        "official_evidence_url": "https://diariodarepublica.pt/",
                    }
                ],
            }
        )

    assert "987–654–321" not in str(error.value)
