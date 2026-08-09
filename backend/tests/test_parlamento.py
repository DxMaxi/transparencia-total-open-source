import asyncio
import hashlib
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


class JsonResponse:
    def __init__(self, url: str, payload: object) -> None:
        self.url = url
        self.content = json.dumps(payload, ensure_ascii=False).encode()
        self.headers = {"content-type": "application/json; charset=utf-8"}


class RawJsonHttp:
    def __init__(self, content: bytes) -> None:
        self.content = content

    async def get(self, url: str, *, max_bytes: int | None = None) -> JsonResponse:
        del max_bytes
        response = JsonResponse(url, {})
        response.content = self.content
        return response


class JsonHttp:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.requested: list[tuple[str, int | None]] = []

    async def get(self, url: str, *, max_bytes: int | None = None) -> JsonResponse:
        self.requested.append((url, max_bytes))
        return JsonResponse(url, self.payload)


class CatalogueHttp:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.requested_urls: list[str] = []

    async def get(self, url: str) -> FakeResponse:
        self.requested_urls.append(url)
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
                (
                    '<a href="/Deputados/Paginas/Acolhimento-XVII.aspx">'
                    "Acolhimento aos Deputados - XVII Legislatura</a>"
                    '<a href="?Path=token&amp;t=token">XVII Legislatura</a>'
                ),
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
    assert http.requested_urls == [catalogue_url, folder_url]


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
                "DepSituacao": {
                    "DadosSituacaoDeputado": [
                        {"sioDes": "Suplente"},
                        {"sioDes": "Efetivo Temporário"},
                    ]
                },
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


def test_excludes_people_who_never_held_a_parliamentary_mandate() -> None:
    payload = [
        {
            "Deputado": {
                "DepId": "601",
                "DepNomeParlamentar": "Pessoa Suplente",
                "DepGP": "AA",
                "DepCPDes": "PORTO",
                "DepSituacao": {"DadosSituacaoDeputado": [{"sioDes": "Suplente"}]},
            }
        },
        {
            "Deputado": {
                "DepId": "602",
                "DepNomeParlamentar": "Pessoa Não Eleita",
                "DepGP": "BB",
                "DepCPDes": "LISBOA",
                "DepSituacao": {"DadosSituacaoDeputado": [{"sioDes": "Suspenso(Não Eleito)"}]},
            }
        },
    ]

    deputies = collector().normalise_deputies(
        payload,
        legislature="XVII",
        source_url="https://app.parlamento.pt/AtividadeDeputadoXVII_json.txt",
        document_sha256="2" * 64,
    )

    assert deputies == []


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
                "DepSituacao": {"DadosSituacaoDeputado": [{"sioDes": "Efetivo"}]},
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
        {
            "Deputado": {
                "DepId": str(index),
                "DepNomeParlamentar": f"Pessoa {index}",
                "DepSituacao": {"DadosSituacaoDeputado": [{"sioDes": "Efetivo"}]},
            }
        }
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
    payload = json.loads((FIXTURES / "parliament_votes.json").read_text(encoding="utf-8"))
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


def test_normalises_official_nested_vote_shape_and_all_position_choices() -> None:
    payload = [
        {
            "IniNr": "1/XVII/1",
            "IniEventos": [
                {
                    "Votacao": [
                        {
                            "id": "139080",
                            "data": "2025-07-04",
                            "descricao": "Votação em Plenário",
                            "detalhe": (
                                "A Favor: <I>PSD</I>, <I> PS</I>"
                                "<BR>Contra:<I>CH</I>"
                                "<BR>Abstenção:<I>IL</I>"
                                "<BR>Ausência: <I>JPP</I>"
                            ),
                            "reuniao": "9",
                            "resultado": "Aprovado",
                        }
                    ],
                    "Comissao": [
                        {
                            "Votacao": [
                                {
                                    "id": "139081",
                                    "data": "2025-07-05",
                                    "detalhe": "A Favor: <I>PSD</I>",
                                    "reuniao": "3",
                                    "resultado": "Aprovado",
                                }
                            ]
                        }
                    ],
                }
            ],
        }
    ]

    events = collector().normalise_votes(
        payload,
        source_url="https://app.parlamento.pt/IniciativasXVII_json.txt",
        document_sha256="3" * 64,
    )

    assert {event.source_id for event in events} == {"139080", "139081"}
    assert {event.initiative_number for event in events} == {"1/XVII/1"}
    plenary = next(event for event in events if event.source_id == "139080")
    assert plenary.is_nominal is False
    assert plenary.voted_at is not None
    assert plenary.voted_at.date().isoformat() == "2025-07-04"
    assert {record.actor_label: record.choice.value for record in plenary.records} == {
        "PSD": "FAVOR",
        "PS": "FAVOR",
        "CH": "AGAINST",
        "IL": "ABSTENTION",
        "JPP": "ABSENT",
    }
    assert {record.actor_type.value for record in plenary.records} == {"UNKNOWN"}


def test_vote_without_description_inherits_the_official_initiative_title() -> None:
    payload = [
        {
            "IniNr": "815",
            "IniDescTipo": "Projeto de Resolução",
            "IniTitulo": "Recomenda a implementação coordenada da terapia fágica",
            "IniEventos": [
                {
                    "Votacao": [
                        {
                            "id": "182700",
                            "data": "2026-07-22",
                            "descricao": None,
                            "detalhe": None,
                            "reuniao": "56",
                            "resultado": "Aprovado",
                        }
                    ]
                }
            ],
        }
    ]

    events = collector().normalise_votes(
        payload,
        source_url="https://app.parlamento.pt/IniciativasXVII_json.txt",
        document_sha256="3" * 64,
    )

    assert events[0].title == (
        "Projeto de Resolução n.º 815 — Recomenda a implementação coordenada da terapia fágica"
    )
    assert events[0].initiative_number == "815"


def test_numeric_vote_description_inherits_the_exact_parent_initiative() -> None:
    payload = [
        {
            "IniId": "356116",
            "IniNr": "416",
            "IniDescTipo": "Projeto de Lei",
            "IniTitulo": "Altera limites territoriais no Município de Penafiel",
            "IniEventos": [
                {
                    "Votacao": [
                        {
                            "id": "172685",
                            "data": "2026-07-17",
                            "descricao": "416",
                            "reuniao": "52",
                            "resultado": "Aprovado",
                        }
                    ]
                }
            ],
        },
        {
            "IniId": "399999",
            "IniNr": "416",
            "IniDescTipo": "Projeto de Resolução",
            "IniTitulo": "Título diferente com o mesmo número",
            "IniEventos": [
                {
                    "Votacao": [
                        {
                            "id": "199999",
                            "data": "2026-07-18",
                            "descricao": "416",
                            "reuniao": "53",
                            "resultado": "Rejeitado",
                        }
                    ]
                }
            ],
        },
    ]

    events = collector().normalise_votes(
        payload,
        source_url="https://app.parlamento.pt/IniciativasXVII_json.txt",
        document_sha256="3" * 64,
    )

    by_id = {event.source_id: event for event in events}
    assert by_id["172685"].title == (
        "Projeto de Lei n.º 416 — Altera limites territoriais no Município de Penafiel"
    )
    assert by_id["199999"].title == (
        "Projeto de Resolução n.º 416 — Título diferente com o mesmo número"
    )


def test_shared_vote_is_not_arbitrarily_linked_to_one_of_multiple_initiatives() -> None:
    vote = {
        "id": "139080",
        "data": "2025-07-04",
        "reuniao": "9",
        "resultado": "Aprovado",
    }
    payload = [
        {"IniNr": "1/XVII/1", "IniEventos": [{"Votacao": [vote]}]},
        {"IniNr": "2/XVII/1", "IniEventos": [{"Votacao": [vote]}]},
    ]

    events = collector().normalise_votes(
        payload,
        source_url="https://app.parlamento.pt/IniciativasXVII_json.txt",
        document_sha256="3" * 64,
    )

    assert len(events) == 1
    assert events[0].initiative_number is None
    assert events[0].title == "Votação conjunta de 2 iniciativas"


def test_marks_exactly_repeated_actor_with_conflicting_positions_as_unknown() -> None:
    payload = {
        "id": "171147",
        "data": "2026-07-01",
        "descricao": "Votação contraditória na fonte",
        "detalhe": "A Favor: <I>PSD</I><BR>Contra: <I> PSD </I>",
        "reuniao": "101",
        "resultado": "Aprovado",
    }

    events = collector().normalise_votes(
        payload,
        source_url="https://app.parlamento.pt/IniciativasXVII_json.txt",
        document_sha256="4" * 64,
    )

    assert len(events) == 1
    assert len(events[0].records) == 1
    assert events[0].records[0].actor_label == "PSD"
    assert events[0].records[0].choice.value == "UNKNOWN"


def test_collect_votes_uses_dedicated_official_file_limit() -> None:
    payload = {
        "id": "139080",
        "data": "2025-07-04",
        "detalhe": "A Favor: <I>PSD</I>",
        "reuniao": "9",
        "resultado": "Aprovado",
    }
    http = JsonHttp(payload)
    settings = Settings(
        environment="test",
        parlamento_votes_url="https://app.parlamento.pt/IniciativasXVII_json.txt",
        parlamento_votes_max_bytes=100_000_000,
    )
    parliament = ParlamentoCollector(settings, http)  # type: ignore[arg-type]

    dataset = asyncio.run(parliament.collect_votes("XVII"))

    assert len(dataset.votes) == 1
    assert http.requested == [("https://app.parlamento.pt/IniciativasXVII_json.txt", 100_000_000)]


def test_fetch_json_hashes_the_exact_received_bytes() -> None:
    raw_document = b'\xef\xbb\xbf{"id": "139080", "resultado": "Aprovado"}'
    http = RawJsonHttp(raw_document)
    parliament = ParlamentoCollector(Settings(environment="test"), http)  # type: ignore[arg-type]

    payload, raw = asyncio.run(
        parliament.fetch_json("https://app.parlamento.pt/IniciativasXVII_json.txt")
    )

    assert payload["id"] == "139080"
    assert str(raw.source_url) == "https://app.parlamento.pt/IniciativasXVII_json.txt"
    assert raw.content_sha256 == hashlib.sha256(raw_document).hexdigest()
    assert (
        raw.content_sha256 != hashlib.sha256(raw_document.decode("utf-8-sig").encode()).hexdigest()
    )
    assert raw.content == raw_document
    assert "content" not in raw.model_dump(mode="json")


def test_collect_votes_warns_when_positions_are_not_normalised() -> None:
    payload = {
        "id": "139080",
        "data": "2025-07-04",
        "detalhe": None,
        "reuniao": "9",
        "resultado": "Aprovado",
    }
    http = JsonHttp(payload)
    parliament = ParlamentoCollector(
        Settings(
            environment="test",
            parlamento_votes_url="https://app.parlamento.pt/IniciativasXVII_json.txt",
        ),
        http,  # type: ignore[arg-type]
    )

    dataset = asyncio.run(parliament.collect_votes("XVII"))

    assert len(dataset.votes) == 1
    assert dataset.votes[0].records == []
    assert any("dados indisponíveis" in warning for warning in dataset.warnings)
