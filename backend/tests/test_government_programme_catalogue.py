import inspect

import pytest

from app.repositories.government_programme_staging import (
    GovernmentProgrammeStagingRepository,
)
from app.services.government_programme_catalogue import (
    GovernmentProgrammeCatalogueError,
    _join_statement,
    _marker,
    _normalise_anchor,
    extract_government_programme_catalogue,
    load_government_programme_manifest,
)
from scripts.publish_government_programme import main as removed_publication_main


def test_manifest_pins_the_complete_reviewed_official_document() -> None:
    manifest = load_government_programme_manifest()

    assert manifest.government_number == "XXV"
    assert manifest.source_url.host == "portugal.gov.pt"
    assert manifest.source_sha256 == (
        "b309badfd59b990774d1552cae8f19968c3d15f202c65ac0d9c2b9c1e3ae1580"
    )
    assert manifest.source_byte_size == 3_543_075
    assert manifest.source_page_count == 252
    assert manifest.expected_candidate_count == 1_590
    assert manifest.expected_catalogue_sha256 == (
        "1b30d61e22e23f712d0b2e0f33e083f8028b9b9038ededf247dabf3da6037d36"
    )
    assert len(manifest.blocks) == 40
    assert sum(block.expected_candidate_count for block in manifest.blocks) == 1_590
    assert len({block.block_id for block in manifest.blocks}) == 40
    assert all(block.expected_block_sha256 != "0" * 64 for block in manifest.blocks)
    assert "candidato PENDING" in manifest.scope_statement


def test_changed_pdf_is_rejected_before_any_parsing() -> None:
    manifest = load_government_programme_manifest()

    with pytest.raises(GovernmentProgrammeCatalogueError, match="bytes"):
        extract_government_programme_catalogue(
            pdf_bytes=b"%PDF-1.7\nconteudo diferente",
            manifest=manifest,
        )


def test_layout_normalisation_is_closed_and_preserves_hierarchy() -> None:
    assert _normalise_anchor("II.  Reforma do Estado") == "II. Reforma do Estado"
    assert _marker("12. Medida principal") == ("12.", 1, "Medida principal")
    assert _marker("a. Desenvolvimento subordinado") == (
        "a.",
        2,
        "Desenvolvimento subordinado",
    )
    assert _marker("▪ Prova complementar") == ("▪", 3, "Prova complementar")
    assert _marker("Uma frase narrativa") is None
    assert _join_statement(["Reforçar a trans-", "parência pública."]) == (
        "Reforçar a transparência pública."
    )


def test_removed_v4_command_can_never_publish_the_catalogue() -> None:
    with pytest.raises(RuntimeError, match="desativada"):
        removed_publication_main()


def test_staging_repository_has_no_public_promise_write_path() -> None:
    source = inspect.getsource(GovernmentProgrammeStagingRepository.stage_catalogue)

    assert "INSERT INTO government_programme_snapshots" in source
    assert "INSERT INTO government_promise_candidates" in source
    assert "INSERT INTO promises" not in source
    assert "INSERT INTO promise_reviews" not in source
    assert '"public_promises_created": 0' in source
    assert '"promise_reviews_created": 0' in source
