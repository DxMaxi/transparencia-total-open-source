import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import HttpUrl

from app.models.archive import PrivateRawDocument, RawArchiveReceipt
from app.services.v4_rollout import (
    DEFAULT_ROLLOUT_SOURCES,
    SOURCE_CONFIGS,
    V4RolloutService,
)
from scripts import bootstrap_v4_public
from scripts.bootstrap_v4_public import (
    EXPECTED_PARLIAMENT_COUNT,
    EXPECTED_PARLIAMENT_SHA256,
)


def test_rollout_covers_every_public_status_source() -> None:
    assert set(DEFAULT_ROLLOUT_SOURCES) == {
        "BASE_CONTRACTS",
        "DRE",
        "TRANSPARENCY_ENTITY",
        "COURT_OF_AUDIT",
        "EUROPEAN_PARLIAMENT",
        "LOCAL_SNS",
    }
    for source_name in DEFAULT_ROLLOUT_SOURCES:
        config = SOURCE_CONFIGS[source_name]
        assert config.url.startswith("https://")
        assert config.publisher
        assert config.title


def test_court_of_audit_uses_current_official_publications_index() -> None:
    assert SOURCE_CONFIGS["COURT_OF_AUDIT"].url == (
        "https://www.tcontas.pt/pt-pt/TribunalContas/Publicacoes/Pages/"
        "Publicacoes-do-Tribunal-de-Contas.aspx"
    )


def test_transparency_entity_keeps_the_canonical_court_endpoint() -> None:
    assert SOURCE_CONFIGS["TRANSPARENCY_ENTITY"].url == (
        "https://www.tribunalconstitucional.pt/tc/ept/"
    )


def test_sns_uses_the_official_transparency_portal() -> None:
    assert SOURCE_CONFIGS["LOCAL_SNS"].url == ("https://transparencia.sns.gov.pt/pages/home-page/")


@pytest.mark.asyncio
async def test_collection_failure_is_recorded_without_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRepository:
        def __init__(self) -> None:
            self.failure: dict[str, object] | None = None
            self.store_called = False

        async def record_failed_index_refresh(self, **kwargs: object) -> str:
            self.failure = kwargs
            return "sync_failed"

        async def store_index(self, **kwargs: object) -> dict[str, object]:
            self.store_called = True
            return kwargs

    repository = FakeRepository()
    service = V4RolloutService(
        object(),  # type: ignore[arg-type]
        repository,  # type: ignore[arg-type]
    )

    async def fail_collection(
        source_name: str,
    ) -> tuple[PrivateRawDocument, list[object]]:
        assert source_name == "LOCAL_SNS"
        raise RuntimeError("fonte temporariamente indisponível")

    monkeypatch.setattr(service, "_collect_source", fail_collection)

    with pytest.raises(RuntimeError, match="temporariamente indisponível"):
        await service.sync_source("LOCAL_SNS")

    assert repository.failure == {
        "source_name": "LOCAL_SNS",
        "dataset_url": "https://transparencia.sns.gov.pt/pages/home-page/",
        "code_version": "v4-public-rollout-v2",
        "error_message": "fonte temporariamente indisponível",
    }
    assert repository.store_called is False


@pytest.mark.asyncio
async def test_rollout_refresh_continues_after_one_source_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = V4RolloutService(object(), object())  # type: ignore[arg-type]
    visited: list[str] = []

    async def fake_sync_source(source_name: str) -> dict[str, object]:
        visited.append(source_name)
        if source_name == "DRE":
            raise RuntimeError("fonte temporariamente indisponível")
        return {"source_name": source_name, "status": "STAGED"}

    monkeypatch.setattr(service, "sync_source", fake_sync_source)
    results = await service.sync_sources(
        ["BASE_CONTRACTS", "DRE", "COURT_OF_AUDIT"]  # type: ignore[list-item]
    )

    assert visited == ["BASE_CONTRACTS", "DRE", "COURT_OF_AUDIT"]
    assert results[0] == {"source_name": "BASE_CONTRACTS", "status": "STAGED"}
    assert results[1]["source_name"] == "DRE"
    assert results[1]["status"] == "FAILED"
    assert results[1]["publication_performed"] is False
    assert results[1]["error_type"] == "RuntimeError"
    assert results[2] == {"source_name": "COURT_OF_AUDIT", "status": "STAGED"}


def test_bootstrap_is_pinned_to_the_audited_parliament_snapshot() -> None:
    review_path = Path(__file__).resolve().parents[2] / "data" / "revisao-deputados-xvii.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    assert review["source_sha256"] == EXPECTED_PARLIAMENT_SHA256
    assert review["candidate_count"] == EXPECTED_PARLIAMENT_COUNT
    assert review["already_published"] == 0
    assert len(review["people"]) == EXPECTED_PARLIAMENT_COUNT


@pytest.mark.asyncio
async def test_changed_parliament_source_is_staged_without_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = b'{"changed": true}'
    current_sha256 = hashlib.sha256(content).hexdigest()
    source_url = HttpUrl("https://app.parlamento.pt/current.json")
    raw_document = PrivateRawDocument(
        source_url=source_url,
        retrieved_at=datetime.now(UTC),
        content_sha256=current_sha256,
        mime_type="application/json",
        content=content,
    )
    dataset = SimpleNamespace(
        raw_document=raw_document,
        deputies=[SimpleNamespace(source_id=str(index)) for index in range(287)],
    )

    class FakeHttpClient:
        def __init__(self, settings: object) -> None:
            self.settings = settings

        async def __aenter__(self) -> "FakeHttpClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeCollector:
        def __init__(self, settings: object, http: object) -> None:
            self.settings = settings
            self.http = http

        async def collect_deputies(self, legislature: str) -> object:
            assert legislature == "XVII"
            return dataset

    class FakeRepository:
        settings = object()

        def __init__(self) -> None:
            self.attestation_called = False
            self.stored_dataset: object | None = None

        async def archive_raw_document(
            self,
            *,
            raw_document: PrivateRawDocument,
        ) -> RawArchiveReceipt:
            return RawArchiveReceipt(
                storage_backend="POSTGRES",
                storage_key=f"sha256/{current_sha256[:2]}/{current_sha256}",
                content_sha256=current_sha256,
                byte_size=len(content),
                mime_type=raw_document.mime_type,
                source_url=raw_document.source_url,
                retrieved_at=raw_document.retrieved_at,
                recorded_at=datetime.now(UTC),
                object_created=True,
            )

        async def store_parliament_dataset(
            self,
            candidate: object,
            **kwargs: object,
        ) -> dict[str, int]:
            self.stored_dataset = candidate
            assert kwargs["kind"] == "deputies"
            assert kwargs["archive_receipt"].content_sha256 == current_sha256
            return {
                "records_read": 287,
                "records_written": 287,
                "records_deactivated": 0,
                "archive_attestations_written": 1,
            }

        async def attest_existing_source_bytes(
            self,
            **kwargs: object,
        ) -> dict[str, object]:
            self.attestation_called = True
            return {}

    monkeypatch.setattr(bootstrap_v4_public, "OfficialHttpClient", FakeHttpClient)
    monkeypatch.setattr(bootstrap_v4_public, "ParlamentoCollector", FakeCollector)
    repository = FakeRepository()

    result = await bootstrap_v4_public.restore_or_stage_parliament_source(
        repository,  # type: ignore[arg-type]
        audited_snapshot={
            "source_url": "https://app.parlamento.pt/audited.json",
            "source_document_id": "source_audited",
        },
    )

    assert result["status"] == "REVIEW_REQUIRED"
    assert result["publication_performed"] is False
    assert result["audited_source_sha256"] == EXPECTED_PARLIAMENT_SHA256
    assert result["current_source_sha256"] == current_sha256
    assert result["current_candidate_count"] == 287
    assert repository.stored_dataset is dataset
    assert repository.attestation_called is False
