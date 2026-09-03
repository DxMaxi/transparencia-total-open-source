"""Porta read-only partilhada pela recolha e pelo diagnóstico operacional."""

from typing import Any

EXACT_VOTE_IDENTITY_MIGRATION = "20260828124500_v5_exact_nominal_vote_identity"


async def exact_vote_identity_schema_is_ready(connection: Any) -> bool:
    """Exige os três objetos V5.45 sem contactar fontes ou alterar dados."""

    return bool(
        await connection.fetchval(
            """
            SELECT
                EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_attribute attribute
                    WHERE attribute.attrelid = to_regclass('public.vote_records')
                      AND attribute.attname = 'actor_source_id'
                      AND NOT attribute.attisdropped
                )
                AND EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_constraint constraint_record
                    WHERE constraint_record.conrelid = to_regclass('public.vote_records')
                      AND constraint_record.conname =
                          'vote_records_actor_source_id_not_blank'
                )
                AND to_regclass(
                    'public.vote_records_person_official_id_per_event_key'
                ) IS NOT NULL
            """
        )
    )
