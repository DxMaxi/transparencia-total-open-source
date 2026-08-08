from datetime import UTC, datetime

from app.models.api import PublishedPromise
from scripts.publish_government_programme import load_catalogue


def test_government_programme_catalogue_is_versioned_and_unambiguous() -> None:
    catalogue = load_catalogue()
    commitments = catalogue["commitments"]

    assert catalogue["governmentNumber"] == "XXV"
    assert len(catalogue["sourceSha256"]) == 64
    assert catalogue["sourceByteSize"] > 1_000_000
    assert len(commitments) == 10
    assert len({item["stableKey"] for item in commitments}) == len(commitments)
    assert all(item["programmePage"].startswith(("p. ", "pp. ")) for item in commitments)


def test_unverified_commitment_does_not_require_implementation_evidence() -> None:
    published = PublishedPromise.model_validate(
        {
            "id": "promise-1",
            "title": "Compromisso oficial",
            "area": "Saúde",
            "status": "UNVERIFIED",
            "progress": 0,
            "programme_page": "p. 27",
            "programme_source": {
                "publisher": "OFICIAL",
                "label": "Programa do Governo",
                "url": "https://portugal.gov.pt/",
                "retrieved_at": datetime(2026, 8, 8, tzinfo=UTC),
                "content_sha256": "a" * 64,
            },
            "rationale": "A execução ainda não foi avaliada.",
            "last_reviewed_at": datetime(2026, 8, 8, tzinfo=UTC),
            "evidence": [],
        }
    )

    assert published.status == "UNVERIFIED"
    assert published.evidence == []
