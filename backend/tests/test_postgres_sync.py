import inspect

from app.repositories.postgres import PostgresRepository


def test_deputy_ingestion_never_deactivates_people_from_a_new_observation() -> None:
    source = inspect.getsource(PostgresRepository.store_parliament_dataset)

    assert "SET active = FALSE" not in source
    assert "UPDATE people" not in source
    assert "ON CONFLICT (source_id) DO NOTHING" in source
    assert "parliamentary_membership_snapshots" in source
    assert "ON CONFLICT (person_id, legislature, source_document_id) DO NOTHING" in source


def test_legacy_vote_persistence_is_removed_from_the_generic_repository() -> None:
    source = inspect.getsource(PostgresRepository.store_parliament_dataset)

    rejection = source.index('if kind == "votes"')
    archive_check = source.index("if archive_receipt is None")
    assert rejection < archive_check
    assert "scripts.sync_parliament_activity" in source
    assert "INSERT INTO vote_events" not in source
    assert "INSERT INTO vote_records" not in source
