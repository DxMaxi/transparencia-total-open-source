import json
from pathlib import Path

from app.services.v4_rollout import DEFAULT_ROLLOUT_SOURCES, SOURCE_CONFIGS
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
