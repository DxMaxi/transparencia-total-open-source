import asyncio
import json
from pathlib import Path

from app.core.config import Settings
from app.services.parlamento import ParlamentoCollector

FIXTURES = Path(__file__).parent / "fixtures"


class NoNetworkHttp:
    pass


class FakeResponse:
    def __init__(self, url: str, text: str) -> None:
        self.url = url
        self.text = text


class CatalogueHttp:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses

    async def get(self, _url: str) -> FakeResponse:
        return self.responses.pop(0)


def collector() -> ParlamentoCollector:
    return ParlamentoCollector(Settings(environment="test"), NoNetworkHttp())  # type: ignore[arg-type]


def test_deputy_catalogue_defaults_to_official_activity_source() -> None:
    assert (
        collector().settings.parlamento_deputies_catalogue_path
        == "/Cidadania/Paginas/DAatividadeDeputado.aspx"
    )


def test_discovers_official_underscore_json_txt_resource() -> None:
    catalogue_url = "https://www.parlamento.pt/Cidadania/Paginas/DAatividadeDeputado.aspx"
    folder_url = f"{catalogue_url}?Path=token&t=token"
    json_url = (
        "https://app.parlamento.pt/webutils/docs/doc.txt?Inline=true"
        "&fich=AtividadeDeputadoXVII_json.txt&path=token"
    )
    http = CatalogueHttp(
        [
            FakeResponse(
                catalogue_url,
                '<a href="?Path=token&amp;t=token">XVII Legislatura</a>',
            ),
            FakeResponse(
                folder_url,
                (
                    '<a href="https://app.parlamento.pt/webutils/docs/doc.txt?Inline=true'
                    '&amp;fich=AtividadeDeputadoXVII.xml&amp;path=token">'
                    "AtividadeDeputadoXVII.xml</a>"
                    '<a href="https://app.parlamento.pt/webutils/docs/doc.txt?Inline=true'
                    '&amp;fich=AtividadeDeputadoXVII_json.txt&amp;path=token">'
                    "AtividadeDeputadoXVII_json.txt</a>"
                ),
            ),
        ]
    )
    parliament = ParlamentoCollector(Settings(environment="test"), http)  # type: ignore[arg-type]

    discovered = asyncio.run(
        parliament.discover_dataset_url(
            parliament.settings.parlamento_deputies_catalogue_path,
            "XVII",
        )
    )

    assert discovered == json_url


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


def test_normalises_only_primary_official_activity_deputy_shape() -> None:
    payload = [
        {
            "Deputado": {
                "DepId": "501",
                "DepCadId": "9001",
                "DepNomeParlamentar": "Pessoa Deputada",
                "DepNomeCompleto": "Pessoa Deputada de Exemplo",
                "DepGP": {
                    "DadosSituacaoGP": [
                        {
                            "gpSigla": "AA",
                            "gpDtInicio": "2025-06-03",
                            "gpDtFim": "2026-01-01",
                        },
                        {"gpSigla": "BB", "gpDtInicio": "2026-01-02"},
                    ]
                },
                "DepCPDes": "PORTO",
            },
            "AtividadeDeputadoList": [
                {
                    "Ini": [
                        {
                            "DepId": "999",
                            "DepNomeParlamentar": "Referência interna",
                            "DepGP": "XX",
                            "DepCPDes": "LISBOA",
                        }
                    ]
                }
            ],
        }
    ]

    deputies = collector().normalise_deputies(
        payload,
        legislature="XVII",
        source_url="https://app.parlamento.pt/AtividadeDeputadoXVII_json.txt",
        document_sha256="d" * 64,
    )

    assert len(deputies) == 1
    assert deputies[0].source_id == "501"
    assert deputies[0].party_short == "BB"
    assert deputies[0].constituency == "PORTO"


def test_does_not_treat_information_base_candidates_as_deputies() -> None:
    payload = {
        "Candidatos": [
            {
                "cadId": 16477.0,
                "NomeParlamentar": "Acardyo Trindade",
                "NomeCompleto": "Acardyo Kedy Santos Nazaré da Trindade",
            }
        ]
    }

    deputies = collector().normalise_deputies(
        payload,
        legislature="XVII",
        source_url="https://app.parlamento.pt/InformacaoBaseXVII_json.txt",
        document_sha256="e" * 64,
    )

    assert deputies == []


def test_rejects_implausible_deputy_snapshot_before_persistence() -> None:
    payload = [
        {
            "Deputado": {
                "DepId": str(index),
                "DepNomeParlamentar": f"Pessoa {index}",
                "DepGP": "AA",
                "DepCPDes": "PORTO",
            }
        }
        for index in range(1, 502)
    ]
    deputies = collector().normalise_deputies(
        payload,
        legislature="XVII",
        source_url="https://app.parlamento.pt/teste.json",
        document_sha256="f" * 64,
    )

    try:
        collector()._validate_deputy_snapshot(deputies)
    except ValueError as exc:
        assert "fora do intervalo de segurança" in str(exc)
    else:
        raise AssertionError("O snapshot anormal deveria ter sido rejeitado")


def test_rejects_snapshot_without_party_and_constituency() -> None:
    payload = [
        {"Deputado": {"DepId": str(index), "DepNomeParlamentar": f"Pessoa {index}"}}
        for index in range(1, 101)
    ]
    deputies = collector().normalise_deputies(
        payload,
        legislature="XVII",
        source_url="https://app.parlamento.pt/teste.json",
        document_sha256="1" * 64,
    )

    try:
        collector()._validate_deputy_snapshot(deputies)
    except ValueError as exc:
        assert "cobertura insuficiente" in str(exc)
    else:
        raise AssertionError("O snapshot sem metadados deveria ter sido rejeitado")


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
