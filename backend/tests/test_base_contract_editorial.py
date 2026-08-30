from copy import deepcopy

import pytest

from app.repositories.base_contract_editorial import (
    _decode_cursor,
    _encode_cursor,
    _json_object_list,
    _validate_base_editorial_payload,
)
from app.repositories.editorial import EditorialSourceError


def _proposal() -> dict[str, object]:
    return {
        "schema_version": "base-contract-editorial-v1",
        "candidate": {
            "official_contract_id": "123456789",
            "object": "Construção de equipamento público",
            "cpv_code": "45000000-7",
            "base_value": "123456789.00",
            "contract_value": "123456789.00",
            "direct_official_url": "https://www.base.gov.pt/Base4/pt/detalhe/?id=1",
            "parties": [
                {
                    "id": "party_1",
                    "ordinal": 0,
                    "role": "CONTRACTOR",
                    "source_name": "Fornecedor Oficial, Lda.",
                    "protected_identifier_observed": True,
                }
            ],
        },
        "source": {
            "title": "Portal BASE — contratos — 2025",
            "url": "https://dados.gov.pt/s/resources/contratos2025.zip",
        },
        "annual_batch": {"resource_title": "contratos2025.zip"},
        "catalogue": {
            "versioned_url": "https://dados.gov.pt/s/resources/20260823/contratos2025.zip",
            "stable_url": "https://dados.gov.pt/api/1/datasets/r/resource-id",
        },
        "archive": {"byte_size": 123456789},
    }


def test_base_specific_validator_accepts_cpv_amount_and_numeric_contract_id() -> None:
    proposal = _proposal()

    assert _validate_base_editorial_payload(proposal) is proposal


def test_base_specific_validator_keeps_free_text_identifier_guard() -> None:
    proposal = deepcopy(_proposal())
    candidate = proposal["candidate"]
    assert isinstance(candidate, dict)
    parties = candidate["parties"]
    assert isinstance(parties, list)
    parties[0]["source_name"] = "123456789 - designação insegura"

    with pytest.raises(ValueError, match="identificadores fiscais|NIF/NIPC"):
        _validate_base_editorial_payload(proposal)


def test_base_cursor_round_trip_supports_timestamp_and_null() -> None:
    item = {
        "batch": {"resource_year": 2025},
        "published_at": "2025-06-01T10:15:00Z",
        "official_contract_id": "BASE-2025-1",
        "contract_snapshot_id": "contract_1",
    }
    cursor = _encode_cursor(item)
    decoded = _decode_cursor(cursor)

    assert decoded[0] == 2025
    assert decoded[1] is not None
    assert decoded[2:] == ("BASE-2025-1", "contract_1")

    item["published_at"] = None
    assert _decode_cursor(_encode_cursor(item))[1] is None


def test_base_cursor_and_json_proof_fail_closed() -> None:
    with pytest.raises(EditorialSourceError, match="Cursor de paginação BASE inválido"):
        _decode_cursor("cursor-adulterado")

    parties, valid = _json_object_list('[{"source_name":"Fornecedor"}]')
    assert valid is True
    assert parties == [{"source_name": "Fornecedor"}]
    assert _json_object_list("{not-json}") == ([], False)
