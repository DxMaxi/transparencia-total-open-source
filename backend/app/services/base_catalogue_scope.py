"""Extrai e verifica o âmbito anual oficial dos contratos do Portal BASE."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import HttpUrl

from app.core.security import require_official_url
from app.models.base_catalogue import (
    BaseCatalogueCoverageState,
    BaseCatalogueResourceScope,
    BaseCatalogueScopeManifest,
    BaseCatalogueTemporalScope,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST_PATH = REPOSITORY_ROOT / "data" / "base-contracts-scope-v1.json"
_RESOURCE_TITLE = re.compile(r"^contratos(?P<year>20[0-9]{2})\.zip$", re.IGNORECASE)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _aware_datetime(value: object, *, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} não está disponível no catálogo oficial")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} não é uma data ISO válida") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} tem de incluir fuso horário")
    return parsed.astimezone(UTC)


def _required_text(value: object, *, label: str, maximum: int = 500) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} está indisponível no catálogo oficial")
    text = " ".join(value.split())
    if not text or len(text) > maximum:
        raise ValueError(f"{label} é inválido no catálogo oficial")
    return text


def load_base_catalogue_manifest(
    path: Path = DEFAULT_MANIFEST_PATH,
) -> BaseCatalogueScopeManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("O manifesto revisto do âmbito BASE não pôde ser lido") from exc
    return BaseCatalogueScopeManifest.model_validate(payload)


def _resource_metadata_payload(
    *,
    source_resource_id: str,
    resource_year: int,
    coverage_state: BaseCatalogueCoverageState,
    title: str,
    versioned_url: str,
    stable_url: str,
    source_modified_at: datetime,
    byte_size: int,
) -> dict[str, object]:
    return {
        "source_resource_id": source_resource_id,
        "resource_year": resource_year,
        "coverage_state": coverage_state.value,
        "title": title,
        "resource_format": "ZIP",
        "versioned_url": versioned_url,
        "stable_url": stable_url,
        "source_modified_at": source_modified_at.isoformat(),
        "byte_size": byte_size,
    }


def _scope_payload(scope: BaseCatalogueTemporalScope) -> dict[str, object]:
    return {
        "schema": "base-contracts-temporal-scope-v1",
        "dataset_id": scope.dataset_id,
        "dataset_title": scope.dataset_title,
        "producer_id": scope.producer_id,
        "producer_name": scope.producer_name,
        "licence_code": scope.licence_code,
        "update_frequency": scope.update_frequency,
        "catalogue_url": str(scope.catalogue_url),
        "public_dataset_url": str(scope.public_dataset_url),
        "catalogue_updated_at": scope.catalogue_updated_at.isoformat(),
        "parser_version": scope.parser_version,
        "policy_version": scope.policy_version,
        "first_year": scope.first_year,
        "closed_through_year": scope.closed_through_year,
        "rolling_year": scope.rolling_year,
        "resources": [
            _resource_metadata_payload(
                source_resource_id=resource.source_resource_id,
                resource_year=resource.resource_year,
                coverage_state=resource.coverage_state,
                title=resource.title,
                versioned_url=str(resource.versioned_url),
                stable_url=str(resource.stable_url),
                source_modified_at=resource.source_modified_at,
                byte_size=resource.byte_size,
            )
            for resource in scope.resources
        ],
    }


def extract_base_catalogue_scope(
    *,
    catalogue_bytes: bytes,
    retrieved_at: datetime,
    manifest: BaseCatalogueScopeManifest,
) -> BaseCatalogueTemporalScope:
    """Conserva um recurso ZIP exato por ano e marca o ano corrente como provisório."""

    if not catalogue_bytes:
        raise ValueError("O catálogo oficial BASE está vazio")
    if retrieved_at.tzinfo is None:
        raise ValueError("A data de recolha do catálogo BASE exige fuso horário")
    observed_at = retrieved_at.astimezone(UTC).replace(
        microsecond=(retrieved_at.microsecond // 1_000) * 1_000
    )
    rolling_year = observed_at.year
    if rolling_year <= manifest.first_year:
        raise ValueError("O ano da recolha não permite definir o âmbito BASE")

    try:
        payload = json.loads(catalogue_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("O catálogo oficial BASE não devolveu JSON válido") from exc
    if not isinstance(payload, dict):
        raise ValueError("O catálogo oficial BASE não tem a estrutura esperada")
    if payload.get("id") != manifest.dataset_id:
        raise ValueError("O catálogo BASE não corresponde ao dataset revisto")
    if payload.get("license") != manifest.licence_code:
        raise ValueError("A licença declarada do dataset BASE diverge do manifesto")
    if payload.get("frequency") != manifest.update_frequency:
        raise ValueError("A frequência declarada do dataset BASE diverge do manifesto")
    if payload.get("private") is not False:
        raise ValueError("O dataset BASE oficial deixou de estar publicamente acessível")

    organisation = payload.get("organization")
    if not isinstance(organisation, dict):
        raise ValueError("O produtor oficial do dataset BASE está indisponível")
    if organisation.get("id") != manifest.producer_id:
        raise ValueError("O produtor do dataset BASE diverge do manifesto revisto")
    producer_name = _required_text(organisation.get("name"), label="Nome do produtor", maximum=300)
    if producer_name != manifest.producer_name:
        raise ValueError("A designação do produtor BASE diverge do manifesto revisto")

    dataset_title = _required_text(payload.get("title"), label="Título do dataset")
    expected_title = (
        "Contratos Públicos - Portal Base - IMPIC - "
        f"Contratos de {manifest.first_year} a {rolling_year}"
    )
    if dataset_title != expected_title:
        raise ValueError("O título do dataset BASE não declara o âmbito anual esperado")
    public_dataset_url = _required_text(payload.get("page"), label="Página pública do dataset")
    require_official_url(public_dataset_url)
    if public_dataset_url.rstrip("/") != str(manifest.public_dataset_url).rstrip("/"):
        raise ValueError("A página pública do dataset BASE diverge do manifesto")

    raw_resources = payload.get("resources")
    if not isinstance(raw_resources, list):
        raise ValueError("Os recursos anuais BASE estão indisponíveis")
    by_year: dict[int, dict[str, Any]] = {}
    for raw_resource in raw_resources:
        if not isinstance(raw_resource, dict):
            continue
        title_value = raw_resource.get("title") or raw_resource.get("name")
        if not isinstance(title_value, str):
            continue
        match = _RESOURCE_TITLE.fullmatch(title_value.strip())
        if match is None:
            continue
        year = int(match.group("year"))
        declared_format = str(raw_resource.get("format") or "").upper()
        if declared_format != manifest.resource_format:
            continue
        if year < manifest.first_year or year > rolling_year:
            raise ValueError("O catálogo BASE contém um recurso ZIP fora do âmbito revisto")
        if year in by_year:
            raise ValueError(f"O catálogo BASE contém mais de um recurso ZIP para {year}")
        by_year[year] = raw_resource

    expected_years = list(range(manifest.first_year, rolling_year + 1))
    missing_years = [year for year in expected_years if year not in by_year]
    if missing_years:
        years = ", ".join(str(year) for year in missing_years)
        raise ValueError(f"Dados indisponíveis: faltam recursos anuais BASE para {years}")

    resources: list[BaseCatalogueResourceScope] = []
    for ordinal, year in enumerate(expected_years):
        raw_resource = by_year[year]
        source_resource_id = _required_text(
            raw_resource.get("id"), label=f"Identificador do recurso BASE {year}", maximum=36
        )
        title = _required_text(raw_resource.get("title"), label=f"Título BASE {year}")
        versioned_url = require_official_url(
            _required_text(
                raw_resource.get("url"),
                label=f"URL versionado BASE {year}",
                maximum=2_000,
            )
        )
        stable_url = require_official_url(
            _required_text(
                raw_resource.get("latest"),
                label=f"URL estável BASE {year}",
                maximum=2_000,
            )
        )
        modified_at = _aware_datetime(
            raw_resource.get("last_modified"), label=f"Atualização do recurso BASE {year}"
        )
        byte_size_value = raw_resource.get("filesize")
        if not isinstance(byte_size_value, int) or isinstance(byte_size_value, bool):
            raise ValueError(f"O tamanho do recurso BASE {year} está indisponível")
        coverage_state = (
            BaseCatalogueCoverageState.CURRENT_ROLLING_YEAR
            if year == rolling_year
            else BaseCatalogueCoverageState.HISTORICAL_CLOSED_YEAR
        )
        metadata = _resource_metadata_payload(
            source_resource_id=source_resource_id,
            resource_year=year,
            coverage_state=coverage_state,
            title=title,
            versioned_url=versioned_url,
            stable_url=stable_url,
            source_modified_at=modified_at,
            byte_size=byte_size_value,
        )
        resources.append(
            BaseCatalogueResourceScope(
                ordinal=ordinal,
                source_resource_id=source_resource_id,
                resource_year=year,
                coverage_state=coverage_state,
                title=title,
                resource_format="ZIP",
                versioned_url=HttpUrl(versioned_url),
                stable_url=HttpUrl(stable_url),
                source_modified_at=modified_at,
                byte_size=byte_size_value,
                metadata_sha256=_sha256_json(metadata),
            )
        )

    source_sha256 = hashlib.sha256(catalogue_bytes).hexdigest()
    provisional = BaseCatalogueTemporalScope(
        dataset_id=manifest.dataset_id,
        dataset_title=dataset_title,
        producer_id=manifest.producer_id,
        producer_name=producer_name,
        licence_code=manifest.licence_code,
        update_frequency=manifest.update_frequency,
        catalogue_url=manifest.catalogue_api_url,
        public_dataset_url=manifest.public_dataset_url,
        catalogue_updated_at=_aware_datetime(
            payload.get("last_modified"), label="Atualização do catálogo BASE"
        ),
        retrieved_at=observed_at,
        source_sha256=source_sha256,
        source_byte_size=len(catalogue_bytes),
        parser_version=manifest.parser_version,
        policy_version=manifest.policy_version,
        first_year=manifest.first_year,
        closed_through_year=rolling_year - 1,
        rolling_year=rolling_year,
        resource_count=len(resources),
        scope_sha256="0" * 64,
        resources=resources,
    )
    scope = provisional.model_copy(
        update={"scope_sha256": _sha256_json(_scope_payload(provisional))}
    )
    verify_base_catalogue_scope(scope=scope, manifest=manifest)
    return scope


def verify_base_catalogue_scope(
    *,
    scope: BaseCatalogueTemporalScope,
    manifest: BaseCatalogueScopeManifest,
) -> None:
    if scope.dataset_id != manifest.dataset_id:
        raise ValueError("O âmbito BASE não corresponde ao manifesto revisto")
    if scope.producer_id != manifest.producer_id or scope.producer_name != manifest.producer_name:
        raise ValueError("O produtor do âmbito BASE não corresponde ao manifesto")
    if scope.catalogue_url != manifest.catalogue_api_url:
        raise ValueError("A fonte do âmbito BASE não corresponde ao manifesto")
    if (
        scope.parser_version != manifest.parser_version
        or scope.policy_version != manifest.policy_version
    ):
        raise ValueError("As versões do âmbito BASE não correspondem ao manifesto")
    if scope.rolling_year != scope.retrieved_at.year:
        raise ValueError("O ano provisório BASE não corresponde à data de recolha")
    for resource in scope.resources:
        metadata = _resource_metadata_payload(
            source_resource_id=resource.source_resource_id,
            resource_year=resource.resource_year,
            coverage_state=resource.coverage_state,
            title=resource.title,
            versioned_url=str(resource.versioned_url),
            stable_url=str(resource.stable_url),
            source_modified_at=resource.source_modified_at,
            byte_size=resource.byte_size,
        )
        if resource.metadata_sha256 != _sha256_json(metadata):
            raise ValueError("O hash de metadados de um recurso BASE é inválido")
    if scope.scope_sha256 != _sha256_json(_scope_payload(scope)):
        raise ValueError("O hash canónico do âmbito BASE é inválido")
