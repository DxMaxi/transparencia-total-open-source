import inspect
from unittest.mock import AsyncMock

import pytest

from app.repositories.postgres import PostgresRepository
from scripts.sync_parliament_activity import _exact_vote_identity_schema_is_ready


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


def test_exact_vote_parser_gate_is_scoped_to_investigator_votes() -> None:
    directory_source = inspect.getsource(PostgresRepository._public_person_rows)
    profile_source = inspect.getsource(PostgresRepository.get_public_politician)
    investigator_source = inspect.getsource(PostgresRepository.get_public_investigator_dataset)

    assert "snapshot.parser_version IN" not in directory_source
    assert "snapshot.parser_version IN" not in profile_source
    assert "snapshot.parser_version IN" in investigator_source
    assert "parliament-activity-v6" in investigator_source
    assert "parliament-historical-votes-v2" in investigator_source
    assert "to_jsonb(vr) ->> 'actor_source_id'" in investigator_source


@pytest.mark.asyncio
@pytest.mark.parametrize(("catalog_result", "expected"), ((True, True), (False, False)))
async def test_parliament_activity_sync_checks_exact_identity_schema_read_only(
    catalog_result: bool,
    expected: bool,
) -> None:
    connection = AsyncMock()
    connection.fetchval.return_value = catalog_result

    assert await _exact_vote_identity_schema_is_ready(connection) is expected

    query = connection.fetchval.await_args.args[0]
    assert "pg_catalog.pg_attribute" in query
    assert "vote_records_actor_source_id_not_blank" in query
    assert "vote_records_person_official_id_per_event_key" in query
    assert "INSERT" not in query
    assert "UPDATE" not in query
    assert "DELETE" not in query
