import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import HttpUrl

from app.models.archive import PrivateRawDocument, RawArchiveReceipt
from app.services.v4_rollout import DEFAULT_ROLLOUT_SOURCES, SOURCE_CONFIGS
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

        async def store_parliament_dataset(self, candidate: object, **kwargs: object) -> dict[str, int]:
            self.stored_dataset = candidate
            assert kwargs["kind"] == "deputies"
            assert kwargs["archive_receipt"].content_sha256 == current_sha256
            return {
                "records_read": 287,
                "records_written": 287,
                "records_deactivated": 0,
                "archive_attestations_written": 1,
            }

        async def attest_existing_source_bytes(self, **kwargs: object) -> dict[str, object]:
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
