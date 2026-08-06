from datetime import UTC, datetime

from app.services.parliamentary_activity import normalise_initiatives, normalise_sessions

SHA = "a" * 64
SOURCE_URL = "https://www.parlamento.pt/dados/atividade.json"
RETRIEVED_AT = datetime(2026, 8, 6, 7, 0, tzinfo=UTC)


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


def test_normalise_initiatives_does_not_invent_missing_status_or_date() -> None:
    payload = {
        "iniciativas": [
            {
                "IniId": "ini-123",
                "IniNr": "1/XVII/1",
                "IniDescTipo": "Projeto de Lei",
                "IniTitulo": "Medida de transparência pública",
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
    assert str(initiative.official_url).startswith("https://www.parlamento.pt/")


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
