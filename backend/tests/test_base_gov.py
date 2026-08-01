import json
from decimal import Decimal
from pathlib import Path

from app.core.config import Settings
from app.models.api import PublicActorMatchKey
from app.services.base_gov import BaseGovCollector, ContractMatcher

FIXTURES = Path(__file__).parent / "fixtures"


class NoNetworkHttp:
    pass


def collector() -> BaseGovCollector:
    return BaseGovCollector(Settings(environment="test"), NoNetworkHttp())  # type: ignore[arg-type]


def test_normalises_base_json_and_keeps_direct_official_source() -> None:
    payload = (FIXTURES / "base_contracts.json").read_bytes()
    rows = list(collector().iter_records(payload, "JSON"))
    contract = collector().normalise_contract(
        rows[0],
        dataset_url="https://dados.gov.pt/api/1/datasets/r/recurso",
        document_sha256="a" * 64,
    )
    assert contract is not None
    assert contract.source_id == "BASE-DEMO-001"
    assert contract.contract_value == Decimal("110500.00")
    assert contract.procedure.value == "PUBLIC_TENDER"
    assert str(contract.direct_official_url).startswith("https://www.base.gov.pt/")
    assert "public_identifier" not in contract.model_dump(mode="json")["contractors"][0]


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
    raw = json.loads((FIXTURES / "base_contracts.json").read_text())
    contract = collector().normalise_contract(
        raw[0],
        dataset_url="https://dados.gov.pt/api/1/datasets/r/recurso",
        document_sha256="b" * 64,
    )
    assert contract is not None
    actor = PublicActorMatchKey.model_validate(
        {
            "person_id": "person-demo",
            "public_name": "Pessoa Pública Demonstrativa",
            "public_role": "DEPUTY",
            "official_role_source_url": (
                "https://www.parlamento.pt/Cidadania/Paginas/DadosAbertos.aspx"
            ),
            "protected_nif": "123456789",
        }
    )
    matches = ContractMatcher(pepper="pepper-de-teste-com-pelo-menos-32-carateres").match(
        [contract],
        [actor],
    )
    assert len(matches) == 1
    assert matches[0].method.value == "EXACT_PROTECTED_IDENTIFIER"
    exported = json.dumps(matches[0].model_dump(mode="json"))
    assert "123456789" not in exported
    assert matches[0].decision == "PENDING_REVIEW"
