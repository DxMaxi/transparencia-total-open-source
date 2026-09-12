"""Exercise the public query against migrated PostgreSQL, without public writes."""

import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
from urllib.parse import urlsplit

import asyncpg
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.models.api import PublishedComparisonMetrics
from app.repositories.postgres import PostgresRepository, _asyncpg_connection_options


@pytest.mark.parametrize("field", ["score", "comparable_pairs", "total_statements"])
def test_individual_pair_cannot_claim_aggregate_metrics(field):
    payload = dict(outcome="CONSISTENT", methodology_version="synthetic-v1", rationale="Proof")
    metrics = PublishedComparisonMetrics(**payload)
    assert metrics.scope == "INDIVIDUAL_PAIR"
    assert metrics.model_dump()[field] is None
    with pytest.raises(ValidationError):
        PublishedComparisonMetrics(**payload, **{field: 98})


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="Disposable PostgreSQL required")
async def test_investigator_query_publication_and_withdrawal_on_migrated_schema():
    dsn = os.environ["DATABASE_URL"]
    assert urlsplit(dsn).hostname in {"localhost", "127.0.0.1", "::1"}
    dsn, settings = _asyncpg_connection_options(dsn)
    connection = await asyncpg.connect(dsn, server_settings=settings)

    @asynccontextmanager
    async def acquire():
        yield connection

    repository = PostgresRepository(Settings(environment="test"))
    repository.pool = SimpleNamespace(acquire=acquire)
    try:
        # Exact migrated column names/types. No constraints or real rows are copied.
        # These session-local tables shadow public tables and disappear on close.
        for table in (
            "interest_relationships",
            "interest_entities",
            "source_documents",
            "public_contracts",
            "source_archive_attestations",
            "editorial_publication_events",
            "parliament_activity_snapshots",
            "data_publication_reviews",
            "public_statements",
            "people",
            "vote_events",
            "vote_records",
            "statement_vote_comparisons",
            "coherence_snapshots",
        ):
            await connection.execute(
                f"CREATE TEMP TABLE {table} AS SELECT * FROM public.{table} WITH NO DATA"
            )
        empty = await repository.get_public_investigator_dataset(limit=10)
        assert empty == {"nodes": [], "edges": [], "comparisons": []}
        await connection.execute("""
            INSERT INTO source_documents
              (id, publisher, url, retrieved_at, content_sha256)
              VALUES ('source', 'PARLIAMENT', 'https://www.parlamento.pt/test',
                      now(), repeat('a',64));
            INSERT INTO source_archive_attestations
              (source_document_id, retrieval_url, content_sha256)
              SELECT id, url, content_sha256 FROM source_documents;
            INSERT INTO people (id, full_name, source_id)
              VALUES ('person', 'Synthetic Person', 'official-1');
            INSERT INTO public_statements (id, person_id, title, statement_text, source_document_id)
              VALUES ('statement', 'person', 'Synthetic statement', 'Synthetic quote', 'source');
            INSERT INTO parliament_activity_snapshots
              (id, legislature, parser_version, source_document_id, collected_at)
              VALUES ('snapshot', 'XVII', 'parliament-activity-v6', 'source', now());
            INSERT INTO data_publication_reviews
              (id, entity_type, entity_id, source_document_id, publishable, reviewed_at)
              VALUES ('review', 'PARLIAMENT_VOTES_SNAPSHOT', 'snapshot', 'source', true, now());
            INSERT INTO vote_events (id, title, snapshot_id, source_document_id, is_nominal)
              VALUES ('vote', 'Synthetic vote', 'snapshot', 'source', true);
            INSERT INTO vote_records
              (id, vote_event_id, person_id, actor_type, actor_source_id,
               source_document_id, choice)
              VALUES ('record', 'vote', 'person', 'PERSON', 'official-1', 'source', 'FAVOR');
            INSERT INTO statement_vote_comparisons
              (id, statement_id, vote_event_id, source_document_id, publication_status,
               verification_status, comparable, outcome, rationale,
               methodology_version, reviewed_at)
              VALUES ('comparison', 'statement', 'vote', 'source', 'PUBLISHED',
                      'VERIFIED', true, 'CONSISTENT', 'Synthetic proof', 'synthetic-v1', now());
            INSERT INTO coherence_snapshots
              (person_id, score, comparable_count, methodology_version, computed_at)
              VALUES ('person', 98, 999, 'unrelated-period-and-method', now());
        """)
        # Legacy flags alone never publish a pair.
        assert not (await repository.get_public_investigator_dataset(limit=10))["comparisons"]
        await connection.execute("""
            INSERT INTO editorial_publication_events
              (id, target_type, target_id, action, created_at)
              VALUES ('publish', 'STATEMENT_VOTE_COMPARISON', 'comparison', 'PUBLISH', now());
        """)
        published = (await repository.get_public_investigator_dataset(limit=10))["comparisons"]
        assert len(published) == 1
        metrics = PublishedComparisonMetrics(**published[0]["comparison"])
        assert metrics.score is metrics.comparable_pairs is metrics.total_statements is None
        await connection.execute("UPDATE vote_records SET actor_source_id = 'different-person'")
        assert not (await repository.get_public_investigator_dataset(limit=10))["comparisons"]
        await connection.execute("UPDATE vote_records SET actor_source_id = 'official-1'")
        await connection.execute("""
            INSERT INTO editorial_publication_events
              (id, target_type, target_id, action, created_at)
              VALUES ('withdraw', 'STATEMENT_VOTE_COMPARISON', 'comparison',
                      'WITHDRAW', now() + interval '1 second');
        """)
        assert not (await repository.get_public_investigator_dataset(limit=10))["comparisons"]
    finally:
        await connection.close()
