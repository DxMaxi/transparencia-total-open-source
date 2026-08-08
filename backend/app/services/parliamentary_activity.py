from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from pydantic import HttpUrl

from app.models.api import OfficialSource, SourcePublisher
from app.models.parliamentary import (
    ParliamentaryInitiativeRecord,
    ParliamentarySessionRecord,
)


def _normalise_key(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _field(record: dict[str, Any], *aliases: str) -> Any | None:
    indexed = {_normalise_key(str(key)): value for key, value in record.items()}
    for alias in aliases:
        value = indexed.get(_normalise_key(alias))
        if value not in (None, "", []):
            return value
    return None


def _text(value: Any | None) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    text = " ".join(str(value).split())
    return text or None


def _nested_text(value: Any | None, *aliases: str) -> str | None:
    direct = _text(value)
    if direct:
        return direct
    if not isinstance(value, (dict, list)):
        return None
    for record in _walk(value):
        candidate = _text(_field(record, *aliases))
        if candidate:
            return candidate
    return None


def _date(value: Any | None) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    candidates = (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    )
    normalised = text.removesuffix("Z")
    for pattern in candidates:
        try:
            return datetime.strptime(normalised, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except ValueError:
        return None


def _walk(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _source(source_url: str, document_sha256: str, retrieved_at: datetime) -> OfficialSource:
    return OfficialSource(
        publisher=SourcePublisher.PARLIAMENT,
        label="Assembleia da República — Dados Abertos",
        url=HttpUrl(source_url),
        retrieved_at=retrieved_at,
        content_sha256=document_sha256,
    )


def normalise_sessions(
    payload: Any,
    *,
    legislature: str,
    source_url: str,
    document_sha256: str,
    retrieved_at: datetime,
) -> list[ParliamentarySessionRecord]:
    source = _source(source_url, document_sha256, retrieved_at)
    sessions: dict[str, ParliamentarySessionRecord] = {}

    for record in _walk(payload):
        explicit_source_id = _text(_field(record, "ReuniaoId", "reuId", "sessionId", "idReuniao"))
        meeting_number = _text(
            _field(record, "ReuniaoNumero", "reuNumero", "sessionNumber", "numeroReuniao")
        )
        meeting_type = _nested_text(
            _field(record, "tipoReuniao", "ReuniaoTipo", "sessionType"),
            "sigla",
            "codigo",
            "tipo",
            "descricao",
            "nome",
        )
        if explicit_source_id is None:
            meeting_number = meeting_number or _text(_field(record, "reuniao"))
        starts_at = _date(
            _field(
                record,
                "ReuniaoData",
                "reuData",
                "sessionDate",
                "dataReuniao",
                "data",
            )
        )
        if (explicit_source_id is None and meeting_number is None) or starts_at is None:
            continue

        source_id = explicit_source_id or (
            "reuniao:"
            f"{_normalise_key(meeting_type or 'tipo-nao-indicado')}:"
            f"{meeting_number}:{starts_at.date().isoformat()}"
        )

        title = _text(
            _field(record, "ReuniaoTitulo", "reuTitulo", "sessionTitle", "descricaoReuniao")
        ) or (
            f"{meeting_type} — reunião {meeting_number}"
            if meeting_type and meeting_number
            else f"Reunião parlamentar {meeting_number or explicit_source_id}"
        )
        ends_at = _date(_field(record, "ReuniaoDataFim", "reuDataFim", "sessionEnd"))
        sessions[source_id] = ParliamentarySessionRecord(
            source_id=source_id,
            legislature=legislature,
            session_number=meeting_number,
            title=title,
            starts_at=starts_at,
            ends_at=ends_at,
            source=source,
        )

    return sorted(sessions.values(), key=lambda item: item.starts_at)


def normalise_initiatives(
    payload: Any,
    *,
    legislature: str,
    source_url: str,
    document_sha256: str,
    retrieved_at: datetime,
    parliament_base_url: str,
) -> list[ParliamentaryInitiativeRecord]:
    source = _source(source_url, document_sha256, retrieved_at)
    initiatives: dict[str, ParliamentaryInitiativeRecord] = {}

    for record in _walk(payload):
        source_id = _text(_field(record, "IniId", "initiativeId", "idIniciativa"))
        number = _text(_field(record, "IniNr", "initiativeNumber", "numeroIniciativa"))
        initiative_type = _text(_field(record, "IniDescTipo", "initiativeType", "tipoIniciativa"))
        title = _text(_field(record, "IniTitulo", "initiativeTitle", "tituloIniciativa"))
        if not source_id or not number or not initiative_type or not title:
            continue

        official_path = _text(
            _field(record, "IniLinkTexto", "IniUrl", "officialUrl", "urlIniciativa")
        )
        official_url = urljoin(parliament_base_url, official_path) if official_path else source_url
        initiatives[source_id] = ParliamentaryInitiativeRecord(
            source_id=source_id,
            legislature=legislature,
            number=number,
            initiative_type=initiative_type,
            title=title,
            description=_text(_field(record, "IniObs", "IniDescricao", "description")),
            introduced_at=_date(_field(record, "IniDataEntrada", "introducedAt")),
            status=_text(_field(record, "IniSituacao", "status", "situacaoIniciativa")),
            official_url=HttpUrl(official_url),
            source=source,
        )

    return sorted(
        initiatives.values(),
        key=lambda item: (item.introduced_at or datetime.min.replace(tzinfo=UTC), item.number),
    )
