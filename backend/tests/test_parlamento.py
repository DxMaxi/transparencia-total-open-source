import json
from pathlib import Path

from app.core.config import Settings
from app.services.parlamento import ParlamentoCollector

FIXTURES = Path(__file__).parent / "fixtures"


class NoNetworkHttp:
    pass


def collector() -> ParlamentoCollector:
    return ParlamentoCollector(Settings(environment="test"), NoNetworkHttp())  # type: ignore[arg-type]


def test_normalises_deputies_without_assuming_optional_fields() -> None:
    payload = json.loads((FIXTURES / "parliament_deputies.json").read_text())
    deputies = collector().normalise_deputies(
        payload,
        legislature="XVII",
        source_url="https://app.parlamento.pt/teste.json",
        document_sha256="a" * 64,
    )
    assert [item.source_id for item in deputies] == ["101", "102"]
    assert deputies[0].party_short == "AA"
    assert deputies[1].full_name is None


def test_only_marks_explicit_person_records_as_nominal() -> None:
    payload = json.loads((FIXTURES / "parliament_votes.json").read_text())
    events = collector().normalise_votes(
        payload,
        source_url="https://app.parlamento.pt/teste-votos.json",
        document_sha256="b" * 64,
    )
    assert len(events) == 1
    assert events[0].is_nominal is True
    assert events[0].records[0].actor_source_id == "101"
    assert events[0].records[1].choice.value == "ABSTENTION"


def test_free_text_party_positions_are_not_attributed_to_people() -> None:
    payload = {
        "VotacaoId": "V-002",
        "VotacaoData": "2026-06-02",
        "VotacaoResultado": "Aprovado",
        "VotacaoDetalhe": "A Favor: AA, BB<BR>Contra: CC",
    }
    events = collector().normalise_votes(
        payload,
        source_url="https://app.parlamento.pt/teste-votos.json",
        document_sha256="c" * 64,
    )
    assert events[0].is_nominal is False
    assert {item.actor_type.value for item in events[0].records} == {"UNKNOWN"}
