import hashlib
import json
from datetime import UTC, datetime

import pytest

from app.models.base_catalogue import BaseCatalogueCoverageState
from app.services.base_catalogue_scope import (
    extract_base_catalogue_scope,
    load_base_catalogue_manifest,
    verify_base_catalogue_scope,
)

RETRIEVED_AT = datetime(2026, 8, 30, 10, 15, 20, 123456, tzinfo=UTC)


def _resource_id(year: int, *, suffix: int = 0) -> str:
    return f"{year:08x}-1234-4abc-8def-{year + suffix:012x}"


def _catalogue_payload(*, missing_year: int | None = None) -> dict[str, object]:
    resources: list[dict[str, object]] = []
    for year in range(2012, 2027):
        if year == missing_year:
            continue
        resource_id = _resource_id(year)
        resources.append(
            {
                "id": resource_id,
                "title": f"contratos{year}.zip",
                "format": "zip",
                "url": (
                    "https://dados.gov.pt/s/resources/contratos-publicos-portal-base-impic-"
                    f"contratos-de-2012-a-2026/20260823-090400/contratos{year}.zip"
                ),
                "latest": f"https://dados.gov.pt/api/1/datasets/r/{resource_id}",
                "last_modified": "2026-08-23T10:04:17.578+01:00",
                "filesize": 10_000_000 + year,
            }
        )
        resources.append(
            {
                "id": _resource_id(year, suffix=100),
                "title": f"contratos{year}.xlsx",
                "format": "xlsx",
                "url": f"https://dados.gov.pt/resources/contratos{year}.xlsx",
                "latest": f"https://dados.gov.pt/api/1/datasets/r/{_resource_id(year, suffix=100)}",
                "last_modified": "2026-08-23T10:04:17.578+01:00",
                "filesize": 20_000_000 + year,
            }
        )
    return {
        "id": "66d72d488ca4b7cb2de28712",
        "title": "Contratos Públicos - Portal Base - IMPIC - Contratos de 2012 a 2026",
        "description": "Contratos de 2012 a 2026.",
        "organization": {
            "id": "5ae97fa2c8d8c915d5faa3bf",
            "name": "IMPIC - Instituto Dos Mercados Públicos, do Imobiliário e da Construção",
        },
        "license": "other-pd",
        "frequency": "weekly",
        "private": False,
        "page": (
            "https://dados.gov.pt/datasets/"
            "contratos-publicos-portal-base-impic-contratos-de-2012-a-2026"
        ),
        "last_modified": "2026-08-24T11:53:45.607+01:00",
        "resources": resources,
    }


def _bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def test_extracts_exact_annual_scope_and_keeps_current_year_provisional() -> None:
    manifest = load_base_catalogue_manifest()
    raw = _bytes(_catalogue_payload())

    scope = extract_base_catalogue_scope(
        catalogue_bytes=raw,
        retrieved_at=RETRIEVED_AT,
        manifest=manifest,
    )

    assert scope.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert scope.first_year == 2012
    assert scope.closed_through_year == 2025
    assert scope.rolling_year == 2026
    assert scope.resource_count == 15
    assert [resource.resource_year for resource in scope.resources] == list(range(2012, 2027))
    assert all(
        resource.coverage_state is BaseCatalogueCoverageState.HISTORICAL_CLOSED_YEAR
        for resource in scope.resources[:-1]
    )
    assert scope.resources[-1].coverage_state is BaseCatalogueCoverageState.CURRENT_ROLLING_YEAR
    assert scope.retrieved_at.microsecond == 123000
    verify_base_catalogue_scope(scope=scope, manifest=manifest)


def test_scope_hash_is_stable_when_official_resource_order_changes() -> None:
    manifest = load_base_catalogue_manifest()
    first_payload = _catalogue_payload()
    second_payload = _catalogue_payload()
    assert isinstance(second_payload["resources"], list)
    second_payload["resources"].reverse()

    first = extract_base_catalogue_scope(
        catalogue_bytes=_bytes(first_payload),
        retrieved_at=RETRIEVED_AT,
        manifest=manifest,
    )
    second = extract_base_catalogue_scope(
        catalogue_bytes=_bytes(second_payload),
        retrieved_at=RETRIEVED_AT,
        manifest=manifest,
    )

    assert first.source_sha256 != second.source_sha256
    assert first.scope_sha256 == second.scope_sha256
    assert [item.metadata_sha256 for item in first.resources] == [
        item.metadata_sha256 for item in second.resources
    ]


def test_missing_year_is_data_unavailable_and_never_silently_partial() -> None:
    with pytest.raises(ValueError, match="Dados indisponíveis.*2018"):
        extract_base_catalogue_scope(
            catalogue_bytes=_bytes(_catalogue_payload(missing_year=2018)),
            retrieved_at=RETRIEVED_AT,
            manifest=load_base_catalogue_manifest(),
        )


def test_duplicate_zip_for_same_year_is_rejected() -> None:
    payload = _catalogue_payload()
    assert isinstance(payload["resources"], list)
    duplicate = dict(payload["resources"][0])
    duplicate["id"] = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    duplicate["latest"] = (
        "https://dados.gov.pt/api/1/datasets/r/aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    )
    payload["resources"].append(duplicate)

    with pytest.raises(ValueError, match="mais de um recurso ZIP"):
        extract_base_catalogue_scope(
            catalogue_bytes=_bytes(payload),
            retrieved_at=RETRIEVED_AT,
            manifest=load_base_catalogue_manifest(),
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("license", "cc-by", "licença"),
        ("frequency", "monthly", "frequência"),
        ("id", "66d72d488ca4b7cb2de287ff", "dataset revisto"),
    ],
)
def test_catalogue_identity_and_terms_fail_closed(
    field: str,
    value: str,
    message: str,
) -> None:
    payload = _catalogue_payload()
    payload[field] = value
    with pytest.raises(ValueError, match=message):
        extract_base_catalogue_scope(
            catalogue_bytes=_bytes(payload),
            retrieved_at=RETRIEVED_AT,
            manifest=load_base_catalogue_manifest(),
        )


def test_stable_resource_url_must_match_official_resource_identifier() -> None:
    payload = _catalogue_payload()
    assert isinstance(payload["resources"], list)
    payload["resources"][0]["latest"] = (
        "https://dados.gov.pt/api/1/datasets/r/ffffffff-ffff-4fff-8fff-ffffffffffff"
    )
    with pytest.raises(ValueError, match="URL estável"):
        extract_base_catalogue_scope(
            catalogue_bytes=_bytes(payload),
            retrieved_at=RETRIEVED_AT,
            manifest=load_base_catalogue_manifest(),
        )


def test_tampered_normalised_hash_is_rejected() -> None:
    manifest = load_base_catalogue_manifest()
    scope = extract_base_catalogue_scope(
        catalogue_bytes=_bytes(_catalogue_payload()),
        retrieved_at=RETRIEVED_AT,
        manifest=manifest,
    )
    tampered = scope.model_copy(update={"scope_sha256": "f" * 64})

    with pytest.raises(ValueError, match="hash canónico"):
        verify_base_catalogue_scope(scope=tampered, manifest=manifest)
