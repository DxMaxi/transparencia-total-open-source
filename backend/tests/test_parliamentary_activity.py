from datetime import UTC, datetime

import pytest

from app.services.parliamentary_activity import normalise_initiatives, normalise_sessions

SHA = "a" * 64
SOURCE_URL = "https://www.parlamento.pt/dados/atividade.json"
RETRIEVED_AT = datetime(2026, 8, 6, 7, 0, tzinfo=UTC)


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_official_legacy_document_link_uses_https_without_changing_evidence(scheme: str) -> None:
    path = "app.parlamento.pt/webutils/docs/doc.pdf?path=616263&fich=source.docx&Inline=true"
    original_url = f"{scheme}://{path}"
    record = {
        "IniId": "initiative-test",
        "IniNr": "1",
        "IniDescTipo": "Projeto de Lei",
        "IniTitulo": "Documento de teste",
        "IniLinkTexto": original_url,
    }
    result = normalise_initiatives(
        [record],
        legislature="XVII",
        source_url=SOURCE_URL,
        document_sha256=SHA,
        retrieved_at=RETRIEVED_AT,
        parliament_base_url="https://www.parlamento.pt",
    )
    assert len(result) == 1
    assert str(result[0].official_url) == f"https://{path}"
    assert str(result[0].source.url) == SOURCE_URL
    assert result[0].source.content_sha256 == SHA
    assert record["IniLinkTexto"] == original_url


@pytest.mark.parametrize(
    "url",
    [
        "http://app.parlamento.pt/webutils/docs/doc.txt?path=test",
        "http://www.parlamento.pt/webutils/docs/doc.pdf?path=test",
        "http://app.parlamento.pt.evil.test/webutils/docs/doc.pdf?path=test",
        "http://user@app.parlamento.pt/webutils/docs/doc.pdf?path=test",
        "http://app.parlamento.pt:8080/webutils/docs/doc.pdf?path=test",
        "https://user@app.parlamento.pt/webutils/docs/doc.pdf?path=test",
        "https://evil.test/webutils/docs/doc.pdf?path=test",
    ],
)
def test_legacy_document_exception_does_not_relax_the_url_guard(url: str) -> None:
    record = {
        "IniId": "initiative-test",
        "IniNr": "1",
        "IniDescTipo": "Projeto de Lei",
        "IniTitulo": "Documento de teste",
        "IniLinkTexto": url,
    }
    with pytest.raises(ValueError, match="URL parlamentar não autorizada"):
        normalise_initiatives(
            [record],
            legislature="XVII",
            source_url=SOURCE_URL,
            document_sha256=SHA,
            retrieved_at=RETRIEVED_AT,
            parliament_base_url="https://www.parlamento.pt",
        )


def test_normalise_sessions_preserves_only_official_fields() -> None:
    payload = {
        "reunioes": [
            {
                "ReuniaoId": "reu-17-1",
                "ReuniaoNumero": "1",
                "ReuniaoTitulo": "Reunião Plenária",
                "ReuniaoData": "2026-07-01T15:00:00",
            },
            {"ReuniaoId": "incompleta"},
        ]
    }

    sessions = normalise_sessions(
        payload,
        legislature="XVII",
        source_url=SOURCE_URL,
        document_sha256=SHA,
        retrieved_at=RETRIEVED_AT,
    )

    assert len(sessions) == 1
    assert sessions[0].source_id == "reu-17-1"
    assert sessions[0].starts_at.tzinfo is UTC
    assert sessions[0].ends_at is None
    assert sessions[0].source.content_sha256 == SHA


def test_normalise_sessions_uses_the_official_vote_meeting_natural_key() -> None:
    payload = {
        "IniEventos": [
            {
                "Votacao": [
                    {
                        "id": "139080",
                        "data": "2025-07-04",
                        "reuniao": "9",
                        "tipoReuniao": "RP",
                        "resultado": "Aprovado",
                    },
                    {
                        "id": "139081",
                        "data": "2025-07-04",
                        "reuniao": "9",
                        "tipoReuniao": "RP",
                        "resultado": "Aprovado",
                    },
                ]
            }
        ]
    }

    sessions = normalise_sessions(
        payload,
        legislature="XVII",
        source_url=SOURCE_URL,
        document_sha256=SHA,
        retrieved_at=RETRIEVED_AT,
    )

    assert len(sessions) == 1
    assert sessions[0].source_id == "reuniao:rp:9:2025-07-04"
    assert sessions[0].session_number == "9"
    assert sessions[0].title == "RP — reunião 9"


def test_normalise_initiatives_does_not_invent_missing_status_or_date() -> None:
    payload = {
        "iniciativas": [
            {
                "IniId": "ini-123",
                "IniNr": "1/XVII/1",
                "IniDescTipo": "Projeto de Lei",
                "IniTitulo": "Medida de transparência pública",
                "dataInicioleg": "2025-06-03",
                "IniObs": "Observação oficial",
                "IniLinkTexto": "/ActividadeParlamentar/Paginas/DetalheIniciativa.aspx?BID=123",
            },
            {
                "IniId": "sem-titulo",
                "IniNr": "2/XVII/1",
                "IniDescTipo": "Projeto de Lei",
            },
        ]
    }

    initiatives = normalise_initiatives(
        payload,
        legislature="XVII",
        source_url=SOURCE_URL,
        document_sha256=SHA,
        retrieved_at=RETRIEVED_AT,
        parliament_base_url="https://www.parlamento.pt",
    )

    assert len(initiatives) == 1
    initiative = initiatives[0]
    assert initiative.source_id == "ini-123"
    assert initiative.status is None
    assert initiative.introduced_at is None
    assert initiative.description == "Observação oficial"
    assert str(initiative.official_url).startswith("https://www.parlamento.pt/")


def test_normalise_initiatives_uses_explicit_entry_and_latest_phase() -> None:
    payload = [
        {
            "IniId": "ini-activity-1",
            "IniNr": "815",
            "IniDescTipo": "Projeto de Resolução",
            "IniTitulo": "Medida pública documentada",
            "IniEventos": [
                {"DataFase": "2026-01-10", "Fase": "Entrada"},
                {"DataFase": "2026-02-03", "Fase": "Admissão"},
                {"DataFase": "2026-07-22", "Fase": "Votação na especialidade"},
            ],
        }
    ]

    initiatives = normalise_initiatives(
        payload,
        legislature="XVII",
        source_url=SOURCE_URL,
        document_sha256=SHA,
        retrieved_at=RETRIEVED_AT,
        parliament_base_url="https://www.parlamento.pt",
    )

    assert initiatives[0].introduced_at == datetime(2026, 1, 10, tzinfo=UTC)
    assert initiatives[0].status == "Votação na especialidade"


def test_normalise_initiatives_deduplicates_by_official_source_id() -> None:
    payload = [
        {
            "IniId": "ini-1",
            "IniNr": "1/XVII/1",
            "IniDescTipo": "Projeto de Lei",
            "IniTitulo": "Versão inicial",
        },
        {
            "IniId": "ini-1",
            "IniNr": "1/XVII/1",
            "IniDescTipo": "Projeto de Lei",
            "IniTitulo": "Versão mais recente observada",
        },
    ]

    initiatives = normalise_initiatives(
        payload,
        legislature="XVII",
        source_url=SOURCE_URL,
        document_sha256=SHA,
        retrieved_at=RETRIEVED_AT,
        parliament_base_url="https://www.parlamento.pt",
    )

    assert len(initiatives) == 1
    assert initiatives[0].title == "Versão mais recente observada"
