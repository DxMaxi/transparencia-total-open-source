import asyncio
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any

from app.repositories.postgres import PostgresRepository


class ReadOnlyAcquire(AbstractAsyncContextManager[Any]):
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    async def __aenter__(self) -> Any:
        return self.connection

    async def __aexit__(self, *_: object) -> None:
        return None


class ReadOnlyPool:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def acquire(self) -> ReadOnlyAcquire:
        return ReadOnlyAcquire(self.connection)


def _repository(connection: Any) -> PostgresRepository:
    repository = PostgresRepository.__new__(PostgresRepository)
    repository.pool = ReadOnlyPool(connection)  # type: ignore[assignment]
    return repository


class VoteInspectionConnection:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def fetchrow(self, query: str, *arguments: object) -> dict[str, Any]:
        self.queries.append(query)
        assert arguments == ("Assembleia da República — votes — XVII",)
        return {
            "sync_run_id": "sync-votes-1",
            "dataset_url": "https://app.parlamento.pt/IniciativasXVII_json.txt",
            "sync_status": "PARTIAL",
            "started_at": datetime(2026, 8, 3, 3, 52, 56),
            "finished_at": datetime(2026, 8, 3, 4, 9, 26),
            "records_read": 2_438,
            "records_written": 22_436,
            "warnings": ["Existem posições cujo ator não é inequivocamente individual."],
            "error_message": None,
            "code_version": "parliament-ingestion-v10",
            "source_document_id": "source-votes-1",
            "source_publisher": "PARLIAMENT",
            "source_kind": "OPEN_DATASET",
            "source_title": "Assembleia da República — votes — XVII",
            "source_url": "https://app.parlamento.pt/IniciativasXVII_json.txt",
            "retrieved_at": datetime(2026, 8, 3, 3, 52, 56),
            "content_sha256": "a" * 64,
            "mime_type": None,
            "raw_storage_key": None,
            "parser_version": "parliament-ingestion-v10",
            "archive_attestation_id": None,
            "archive_storage_backend": None,
            "archive_storage_key": None,
            "archive_content_sha256": None,
            "archive_byte_size": None,
            "archive_mime_type": None,
            "archive_retrieval_url": None,
            "archive_retrieved_at": None,
            "archive_archived_at": None,
            "archive_archived_by": None,
            "archive_attestation_sha256": None,
            "event_count": 2_438,
            "position_count": 19_998,
            "nominal_event_count": 0,
            "event_without_date_count": 0,
            "event_without_normalised_positions_count": 342,
            "unknown_choice_count": 7,
            "person_link_count": 0,
            "party_link_count": 0,
        }

    async def fetch(self, query: str, *arguments: object) -> list[dict[str, Any]]:
        self.queries.append(query)
        assert arguments == ("source-votes-1",)
        if "AS dimension" in query:
            return [
                {"dimension": "choice", "value": "FAVOR", "count": 11_395},
                {"dimension": "choice", "value": "AGAINST", "count": 3_981},
                {"dimension": "choice", "value": "ABSTENTION", "count": 3_325},
                {"dimension": "choice", "value": "ABSENT", "count": 1_290},
                {"dimension": "choice", "value": "UNKNOWN", "count": 7},
                {"dimension": "actor_type", "value": "UNKNOWN", "count": 19_998},
            ]
        return [
            {
                "source_id": f"vote-{index}",
                "title": f"Votação {index}",
                "voted_at": None,
                "result": "Aprovado",
            }
            for index in range(342)
        ]


def test_vote_staging_inspection_is_read_only_and_reports_uncertainty() -> None:
    connection = VoteInspectionConnection()

    report = asyncio.run(
        _repository(connection).inspect_parliament_votes_staging(legislature="XVII")
    )

    assert report["publication_eligible"] is False
    assert report["counts"] == {
        "events": 2_438,
        "positions": 19_998,
        "nominal_events": 0,
        "events_without_date": 0,
        "events_without_normalised_positions": 342,
        "unknown_choices": 7,
        "person_links": 0,
        "party_links": 0,
    }
    availability = report["normalised_position_availability"]
    assert availability["event_count"] == 342
    assert "confirmar no documento oficial" in availability["description"]
    assert "parser" in availability["description"]
    assert report["provenance"]["archive_attestation"] is None
    assert report["checks"]["archive_attested"] is False
    assert report["checks"]["archive_hash_matches_source"] is False
    assert report["checks"]["archive_url_matches_source"] is False
    assert report["checks"]["archive_key_matches_source_hash"] is False
    assert all(value for key, value in report["checks"].items() if not key.startswith("archive_"))
    assert len(connection.queries) == 3
    assert all(query.lstrip().startswith("SELECT") for query in connection.queries)
    snapshot_query = connection.queries[0]
    assert "source.parser_version = run.code_version" in snapshot_query
    assert "MIN(event.updated_at) >= run.started_at" in snapshot_query
    assert "MAX(event.updated_at) <= run.finished_at" in snapshot_query
    assert "COUNT(DISTINCT event.id) = run.records_read" in snapshot_query
    assert "COUNT(DISTINCT event.id) + COUNT(record.id) = run.records_written" in snapshot_query
    assert "source_archive_attestations candidate" in snapshot_query
    assert "LEFT JOIN LATERAL" in snapshot_query


class PublicProfileConnection:
    def __init__(self, *, nominal_vote_count: int = 0) -> None:
        self.membership_query = ""
        self.mandate_query = ""
        self.attendance_query = ""
        self.availability_query = ""
        self.vote_query = ""
        self.declaration_query = ""
        self.nominal_vote_count = nominal_vote_count

    async def fetch(self, query: str, *arguments: object) -> list[dict[str, Any]]:
        if "FROM people p" in query:
            return [
                {
                    "id": "person-1",
                    "slug": "pessoa-1",
                    "name": "Pessoa 1",
                    "role": "DEPUTY",
                    "photo_url": None,
                    "party": "Partido",
                    "party_short": "P",
                    "constituency": "Lisboa",
                    "legislature": "XVII",
                    "observed_at": datetime(2026, 8, 1),
                    "verified_at": datetime(2026, 8, 1),
                    "source_publisher": "PARLIAMENT",
                    "source_url": "https://www.parlamento.pt/",
                    "source_retrieved_at": datetime(2026, 8, 1),
                    "source_sha256": "b" * 64,
                }
            ]
        if "FROM parliamentary_membership_snapshots membership" in query:
            self.membership_query = query
        elif "FROM mandates mandate" in query:
            self.mandate_query = query
        elif "FROM asset_declaration_metadata adm" in query:
            self.declaration_query = query
        elif "FROM vote_records vr" in query:
            self.vote_query = query
        return []

    async def fetchrow(self, query: str, *arguments: object) -> dict[str, Any] | None:
        if "latest_published_activity_snapshot" in query:
            self.attendance_query = query
            return None
        if "latest_published_vote_snapshot" in query:
            self.availability_query = query
            return {
                "verified_at": datetime(2026, 8, 1),
                "source_publisher": "PARLIAMENT",
                "source_url": "https://www.parlamento.pt/",
                "source_retrieved_at": datetime(2026, 8, 1),
                "source_sha256": "b" * 64,
                "nominal_vote_count": self.nominal_vote_count,
                "observed_from": None,
                "observed_through": None,
            }
        return None


def _public_profile_result(
    *, nominal_vote_count: int = 0
) -> tuple[dict[str, Any], PublicProfileConnection]:
    connection = PublicProfileConnection(nominal_vote_count=nominal_vote_count)
    profile = asyncio.run(_repository(connection).get_public_politician("pessoa-1"))
    assert profile is not None
    return profile, connection


def test_public_vote_gate_returns_no_votes_without_review() -> None:
    profile, connection = _public_profile_result()

    assert profile["nominal_votes_available"] is False
    assert profile["nominal_vote_count"] == 0
    assert profile["votes"] == []
    for query in (connection.availability_query, connection.vote_query):
        assert "entity_type = 'PARLIAMENT_VOTES_SNAPSHOT'" in query
        assert "JOIN LATERAL" in query
        assert "LEFT JOIN LATERAL" not in query
        assert "publishable = TRUE" in query
        assert "source_archive_attestations" in query


def test_profile_uses_reviewed_total_instead_of_limited_vote_list_length() -> None:
    profile, connection = _public_profile_result(nominal_vote_count=73)

    assert profile["nominal_votes_available"] is True
    assert profile["nominal_vote_count"] == 73
    assert profile["votes"] == []
    assert "SELECT COUNT(*)" in connection.availability_query
    assert "LIMIT 50" not in connection.availability_query
    assert "LIMIT 50" in connection.vote_query


def test_latest_negative_vote_review_revokes_an_older_positive_review() -> None:
    _, connection = _public_profile_result()

    for query, review_alias in (
        (connection.availability_query, "candidate"),
        (connection.vote_query, "review"),
    ):
        order_position = query.index(
            f"ORDER BY {review_alias}.reviewed_at DESC, {review_alias}.id DESC"
        )
        selection_position = query.rfind(f"SELECT {review_alias}.publishable", 0, order_position)
        limit_position = query.index("LIMIT 1", order_position)
        gate_position = query.index("publishable = TRUE", limit_position)
        review_selection = query[selection_position:limit_position]
        assert f"{review_alias}.publishable = TRUE" not in review_selection
        assert selection_position < order_position < limit_position < gate_position


def test_review_of_old_source_does_not_authorise_a_new_vote_snapshot() -> None:
    _, connection = _public_profile_result()

    for query in (connection.availability_query, connection.vote_query):
        assert "entity_id = snapshot.id" in query
        assert "source_document_id = source.id" in query
        assert "snapshot.parser_version = $3" in query
    assert "available_event.snapshot_id = published.id" in connection.availability_query
    assert "published_snapshot.id = ve.snapshot_id" in connection.vote_query
    assert "available_record.person_id = $1" in connection.availability_query
    assert "available_record.actor_type = 'PERSON'" in connection.availability_query
    assert "available_record.choice IN" in connection.availability_query
    assert "'FAVOR', 'AGAINST', 'ABSTENTION', 'ABSENT'" in connection.availability_query
    assert "'PAIRED'" not in connection.availability_query
    assert "available_record.source_document_id =" in connection.availability_query
    assert "available_event.source_document_id" in connection.availability_query
    assert "vr.source_document_id = ve.source_document_id" in connection.vote_query
    assert "sd.publisher = 'PARLIAMENT'" in connection.vote_query
    assert "vr.choice IN ('FAVOR', 'AGAINST', 'ABSTENTION', 'ABSENT')" in connection.vote_query
    assert "'PAIRED'" not in connection.vote_query
    assert "source_archive_attestations vote_archive" in connection.vote_query


def test_v56_profile_areas_have_independent_fail_closed_publication_gates() -> None:
    profile, connection = _public_profile_result()

    assert profile["contract_version"] == "v5.6"
    assert profile["coverage"]["initiatives"]["state"] == "UNAVAILABLE"
    assert profile["declarations"] == []
    assert profile["declaration"] is None
    assert profile["declaration_source"] is None
    assert "não confirma" in profile["declaration_lookup_source"]["note"]

    assert "review.entity_type = 'PERSON'" in connection.membership_query
    assert "HAVING COUNT(*)" in connection.membership_query
    assert "source_archive_attestations archive" in connection.membership_query

    assert "candidate.entity_type = 'MANDATE'" in connection.mandate_query
    assert "ORDER BY candidate.reviewed_at DESC, candidate.id DESC" in connection.mandate_query
    assert "source.publisher <> 'MEDIA'" in connection.mandate_query
    assert "source_archive_attestations mandate_archive" in connection.mandate_query

    assert "candidate.entity_type = 'PARLIAMENT_ACTIVITY_SNAPSHOT'" in connection.attendance_query
    assert "candidate.entity_type = 'MANDATE'" in connection.attendance_query
    assert "mandate_review.publishable = TRUE" in connection.attendance_query
    assert "source_archive_attestations activity_archive" in connection.attendance_query
    assert "source_archive_attestations mandate_archive" in connection.attendance_query

    assert "snapshot.parser_version = $3" in connection.availability_query
    assert "exact_person.source_id IS NOT NULL" in connection.availability_query
    assert "snapshot.parser_version = $3" in connection.vote_query
    assert "exact_person.source_id IS NOT NULL" in connection.vote_query

    assert "candidate.entity_type = 'ASSET_DECLARATION'" in connection.declaration_query
    assert "sd.publisher = 'TRANSPARENCY_ENTITY'" in connection.declaration_query
    assert "source_archive_attestations declaration_archive" in connection.declaration_query


class InvestigatorConnection:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def fetch(self, query: str, *arguments: object) -> list[dict[str, Any]]:
        self.queries.append(query)
        if len(self.queries) == 1:
            assert arguments == (25,)
        else:
            assert arguments == ()
        return []


def test_public_investigator_uses_the_same_vote_snapshot_gate() -> None:
    connection = InvestigatorConnection()

    report = asyncio.run(_repository(connection).get_public_investigator_dataset(limit=25))

    assert report["nodes"] == []
    assert report["edges"] == []
    assert report["comparisons"] == []
    assert len(connection.queries) == 2
    comparison_query = connection.queries[1]
    assert "review.entity_type = 'PARLIAMENT_VOTES_SNAPSHOT'" in comparison_query
    assert "review.entity_id = snapshot.id" in comparison_query
    assert "review.source_document_id = source.id" in comparison_query
    assert "ORDER BY review.reviewed_at DESC, review.id DESC" in comparison_query
    assert "latest_review.publishable = TRUE" in comparison_query
    assert "published_vote_snapshot.id = ve.snapshot_id" in comparison_query
    assert "vr.source_document_id = ve.source_document_id" in comparison_query
    assert "vote_sd.id = ve.source_document_id" in comparison_query
    assert "ve.is_nominal = TRUE" in comparison_query
    assert "vote_sd.publisher = 'PARLIAMENT'" in comparison_query
    assert "vr.choice IN ('FAVOR', 'AGAINST', 'ABSTENTION', 'ABSENT')" in comparison_query
    assert "'PAIRED'" not in comparison_query
    assert "source_archive_attestations vote_archive" in comparison_query
    assert "source_archive_attestations statement_archive" in comparison_query
