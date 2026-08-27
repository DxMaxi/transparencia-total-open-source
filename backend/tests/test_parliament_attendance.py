import hashlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.models.parliamentary_attendance import ParliamentAttendanceStatus
from app.services.parliament_attendance import (
    PARLIAMENT_ATTENDANCE_PARSER_VERSION,
    ParliamentAttendanceCollector,
    ParliamentAttendanceNormalizer,
    ParliamentAttendanceStager,
    require_attendance_url,
)
from scripts.sync_parliament_attendance import validate_private_attendance_operation

MEETING_URL = "https://www.parlamento.pt/DeputadoGP/Paginas/DetalheReuniaoPlenaria.aspx?BID=376838"


def _attendance_html(*, count: int = 100, duplicate_conflict: bool = False) -> bytes:
    rows: list[str] = []
    for index in range(count):
        if index == 0:
            status = "Falta Justificada (FJ)"
            reason = "<span>Motivo</span><span>Força Maior</span>"
        elif index == 1:
            status = "Falta Injustificada (FI)"
            reason = ""
        elif index == 2:
            status = "Estado por confirmar (X)"
            reason = ""
        else:
            status = "Presença (P)"
            reason = ""
        rows.append(
            "<tr>"
            "<td>Deputado "
            f'<a href="/DeputadoGP/Paginas/Biografia.aspx?BID={7000 + index}">'
            f"Pessoa Deputada {index:03d}</a></td>"
            f"<td>Grupo Parlamentar/Partido G{index % 5}</td>"
            f"<td>Presença/Falta {status}</td>"
            f"<td>{reason}</td>"
            "</tr>"
        )
    if duplicate_conflict:
        rows.append(
            "<tr><td>Deputado "
            '<a href="/DeputadoGP/Paginas/Biografia.aspx?BID=7000">Outra Pessoa</a>'
            "</td><td>Grupo Parlamentar/Partido GX</td>"
            "<td>Presença/Falta Presença (P)</td></tr>"
        )
    return (
        "<html><body>"
        "<nav>Bem-vindo à Reunião Plenária e às opções de consulta</nav>"
        "<h1>Reunião Plenária Ordinária de 2026-07-17.</h1>"
        "<table>" + "".join(rows) + "</table>"
        '<a href="https://app.parlamento.pt/webutils/docs/doc.pdf?'
        'Fich=XVII_1_111_2026-07-17.pdf&amp;Inline=true">PDF oficial</a>'
        "</body></html>"
    ).encode()


def _response(body: bytes, *, url: str = MEETING_URL) -> httpx.Response:
    return httpx.Response(
        200,
        content=body,
        headers={"content-type": "text/html; charset=utf-8"},
        request=httpx.Request("GET", url),
    )


@pytest.mark.asyncio
async def test_collector_preserves_meeting_deputy_ids_statuses_and_hash() -> None:
    body = _attendance_html()
    http = AsyncMock()
    http.get.return_value = _response(body)

    result = await ParliamentAttendanceCollector(http).collect(
        legislature="XVII",
        meeting_url=MEETING_URL,
    )

    assert result.parser_version == PARLIAMENT_ATTENDANCE_PARSER_VERSION
    assert result.official_meeting_id == "376838"
    assert result.meeting_date.isoformat() == "2026-07-17"
    assert result.meeting_type == "Ordinária"
    assert result.session_number == "111"
    assert result.document_sha256 == hashlib.sha256(body).hexdigest()
    assert result.raw_document is not None
    assert result.raw_document.content == body
    assert len(result.observations) == 100
    by_id = {item.official_deputy_id: item for item in result.observations}
    assert by_id["7000"].status is ParliamentAttendanceStatus.JUSTIFIED_ABSENCE
    assert by_id["7000"].absence_reason == "Força Maior"
    assert by_id["7001"].status is ParliamentAttendanceStatus.UNJUSTIFIED_ABSENCE
    assert by_id["7002"].status is ParliamentAttendanceStatus.UNKNOWN
    assert by_id["7003"].status is ParliamentAttendanceStatus.PRESENT
    assert by_id["7003"].parliamentary_group_label == "G3"
    assert "não prova assiduidade" in result.warnings[0]
    assert "1 estados" in result.warnings[2]


def test_normalizer_rejects_duplicate_bid_and_implausible_count() -> None:
    body = _attendance_html(duplicate_conflict=True)
    from app.models.archive import PrivateRawDocument

    document = PrivateRawDocument(
        source_url=MEETING_URL,
        retrieved_at=datetime(2026, 8, 27, tzinfo=UTC),
        content_sha256=hashlib.sha256(body).hexdigest(),
        mime_type="text/html",
        content=body,
    )
    with pytest.raises(ValueError, match="mesmo BID oficial.*divergentes"):
        ParliamentAttendanceNormalizer().normalise(document, legislature="XVII")

    short_body = _attendance_html(count=99)
    short_document = PrivateRawDocument(
        source_url=MEETING_URL,
        retrieved_at=datetime(2026, 8, 27, tzinfo=UTC),
        content_sha256=hashlib.sha256(short_body).hexdigest(),
        mime_type="text/html",
        content=short_body,
    )
    with pytest.raises(ValueError, match="fora do intervalo de segurança"):
        ParliamentAttendanceNormalizer().normalise(short_document, legislature="XVII")


@pytest.mark.parametrize(
    "url",
    (
        "http://www.parlamento.pt/DeputadoGP/Paginas/DetalheReuniaoPlenaria.aspx?BID=1",
        "https://www.parlamento.pt/DeputadoGP/Paginas/Biografia.aspx?BID=1",
        ("https://www.parlamento.pt/DeputadoGP/Paginas/DetalheReuniaoPlenaria.aspx?BID=nome"),
        ("https://www.parlamento.pt/DeputadoGP/Paginas/DetalheReuniaoPlenaria.aspx?BID=1&extra=2"),
        ("https://www.parlamento.pt/DeputadoGP/Paginas/DetalheReuniaoPlenaria.aspx?BID=1&bid=2"),
    ),
)
def test_attendance_url_fails_closed(url: str) -> None:
    with pytest.raises(ValueError):
        require_attendance_url(url)


@pytest.mark.asyncio
async def test_stager_revalidates_bytes_and_does_not_create_editorial_case() -> None:
    body = _attendance_html()
    http = AsyncMock()
    http.get.return_value = _response(body)
    dataset = await ParliamentAttendanceCollector(http).collect(
        legislature="XVII",
        meeting_url=MEETING_URL,
    )
    repository = AsyncMock()
    repository.persist_private_attendance.return_value = {
        "sync_run_id": "sync_fixture",
        "normalised_snapshot_id": "parliament_attendance_snapshot_fixture",
        "record_count": 100,
        "sync_status": "PARTIAL",
        "publishable": False,
    }

    result = await ParliamentAttendanceStager(Settings(environment="test"), repository).store(
        dataset
    )

    assert result["records_normalised"] == 100
    assert result["editorial_cases_created"] == 0
    assert result["publication_performed"] is False
    assert result["publishable"] is False
    repository.persist_private_attendance.assert_awaited_once_with(dataset)

    altered = dataset.observations[0].model_copy(update={"parliamentary_name": "Nome alterado"})
    altered_dataset = dataset.model_copy(
        update={"observations": (altered, *dataset.observations[1:])}
    )
    with pytest.raises(ValueError, match="não coincide com os bytes revalidados"):
        await ParliamentAttendanceStager(Settings(environment="test"), repository).store(
            altered_dataset
        )


@pytest.mark.asyncio
async def test_stager_rejects_production_and_missing_raw_bytes() -> None:
    body = _attendance_html()
    http = AsyncMock()
    http.get.return_value = _response(body)
    dataset = await ParliamentAttendanceCollector(http).collect(
        legislature="XVII",
        meeting_url=MEETING_URL,
    )
    repository = AsyncMock()

    with pytest.raises(RuntimeError, match="test ou staging"):
        await ParliamentAttendanceStager(Settings(environment="production"), repository).store(
            dataset
        )
    with pytest.raises(ValueError, match="não conserva os bytes"):
        await ParliamentAttendanceStager(Settings(environment="test"), repository).store(
            dataset.model_copy(update={"raw_document": None})
        )
    repository.persist_private_attendance.assert_not_awaited()


def test_script_requires_explicit_staging_and_database() -> None:
    with pytest.raises(RuntimeError, match="confirm-private-staging"):
        validate_private_attendance_operation(Settings(environment="staging"), confirmed=False)
    with pytest.raises(RuntimeError, match="ENVIRONMENT tem de ser staging"):
        validate_private_attendance_operation(Settings(environment="test"), confirmed=True)
    with pytest.raises(RuntimeError, match="DATABASE_URL de staging"):
        validate_private_attendance_operation(
            Settings(environment="staging", database_url=None), confirmed=True
        )
    validate_private_attendance_operation(
        Settings(
            environment="staging",
            database_url="postgresql://staging.example.invalid/tt",
        ),
        confirmed=True,
    )
