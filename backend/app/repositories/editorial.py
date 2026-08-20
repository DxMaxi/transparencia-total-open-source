"""Persistência transacional do circuito editorial privado V5."""

import base64
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import asyncpg

from app.models.editorial import (
    EditorialAction,
    EditorialCaseCreateRequest,
    EditorialCaseKind,
    EditorialCorrectionRequest,
    EditorialOrigin,
    EditorialState,
    StaffRole,
    StaffSession,
    validate_normalized_data,
)


class EditorialNotFoundError(LookupError):
    pass


class EditorialConflictError(ValueError):
    pass


class EditorialSourceError(ValueError):
    pass


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _as_json(value: object) -> object:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _encode_cursor(created_at: datetime, case_id: str) -> str:
    raw = _canonical_json([_aware(created_at).isoformat(), case_id]).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    if len(cursor) > 512:
        raise EditorialConflictError("Cursor de paginação inválido")
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding))
        if not isinstance(payload, list) or len(payload) != 2:
            raise ValueError
        created_at = datetime.fromisoformat(str(payload[0])).astimezone(UTC).replace(tzinfo=None)
        case_id = str(payload[1])
        if not case_id or len(case_id) > 200:
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise EditorialConflictError("Cursor de paginação inválido") from exc
    return created_at, case_id


class EditorialRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def staff_session(
        self,
        *,
        auth_user_id: uuid.UUID,
        assurance_level: str,
    ) -> StaffSession:
        row = await self.pool.fetchrow(
            """
            SELECT id, auth_user_id, public_alias, role
            FROM staff_profiles
            WHERE auth_user_id = $1 AND active = TRUE
            """,
            auth_user_id,
        )
        if row is None:
            raise EditorialNotFoundError("Conta sem autorização editorial ativa")
        if assurance_level not in {"aal1", "aal2"}:
            raise EditorialConflictError("Nível de autenticação inválido")
        return StaffSession(
            staff_id=str(row["id"]),
            auth_user_id=cast(uuid.UUID, row["auth_user_id"]),
            public_alias=str(row["public_alias"]),
            role=StaffRole(str(row["role"])),
            assurance_level=cast(Any, assurance_level),
            mfa_required=assurance_level != "aal2",
        )

    async def list_cases(
        self,
        *,
        state: EditorialState | None,
        kind: EditorialCaseKind | None,
        limit: int,
        cursor: str | None,
    ) -> dict[str, object]:
        conditions = ["c.current_version_id IS NOT NULL"]
        arguments: list[object] = []
        if state is not None:
            arguments.append(state.value)
            conditions.append(f'c.current_state = ${len(arguments)}::"EditorialState"')
        if kind is not None:
            arguments.append(kind.value)
            conditions.append(f'c.kind = ${len(arguments)}::"EditorialCaseKind"')
        if cursor is not None:
            created_at, case_id = _decode_cursor(cursor)
            arguments.extend([created_at, case_id])
            conditions.append(f"(c.created_at, c.id) < (${len(arguments) - 1}, ${len(arguments)})")
        arguments.append(limit + 1)
        query = f"""
            SELECT
                c.id,
                c.kind,
                c.subject_type,
                c.subject_id,
                c.current_state,
                c.revision,
                c.origin,
                c.created_by_alias,
                c.created_at,
                c.updated_at,
                v.version_number,
                v.normalized_sha256,
                source.title AS source_title,
                source.publisher AS source_publisher,
                source.url AS source_url,
                source.retrieved_at AS source_retrieved_at,
                source.content_sha256 AS source_sha256
            FROM editorial_cases AS c
            JOIN editorial_versions AS v ON v.id = c.current_version_id
            JOIN source_documents AS source ON source.id = c.source_document_id
            WHERE {" AND ".join(conditions)}
            ORDER BY c.created_at DESC, c.id DESC
            LIMIT ${len(arguments)}
        """
        rows = await self.pool.fetch(query, *arguments)
        has_more = len(rows) > limit
        visible_rows = rows[:limit]
        items = [self._case_summary(row) for row in visible_rows]
        next_cursor = None
        if has_more and visible_rows:
            last = visible_rows[-1]
            next_cursor = _encode_cursor(last["created_at"], str(last["id"]))

        count_rows = await self.pool.fetch(
            """
            SELECT current_state, count(*) AS total
            FROM editorial_cases
            WHERE current_version_id IS NOT NULL
            GROUP BY current_state
            """
        )
        counts = {state_value.value: 0 for state_value in EditorialState}
        for row in count_rows:
            counts[str(row["current_state"])] = int(row["total"])
        return {"items": items, "next_cursor": next_cursor, "counts": counts}

    async def list_source_candidates(
        self,
        *,
        query: str | None,
        limit: int,
    ) -> list[dict[str, object]]:
        search = query.strip() if query else None
        arguments: list[object] = []
        condition = ""
        if search:
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            arguments.append(f"%{escaped}%")
            condition = """
                AND (
                    source.title ILIKE $1 ESCAPE '\\'
                    OR COALESCE(source.official_identifier, '') ILIKE $1 ESCAPE '\\'
                    OR source.url ILIKE $1 ESCAPE '\\'
                )
            """
        arguments.append(limit)
        rows = await self.pool.fetch(
            f"""
            SELECT
                source.id,
                source.publisher,
                source.kind,
                source.title,
                source.official_identifier,
                source.url,
                source.retrieved_at,
                source.published_at,
                source.content_sha256,
                source.mime_type,
                count(DISTINCT cases.id) AS editorial_case_count
            FROM source_documents AS source
            JOIN source_archive_attestations AS archive
             ON archive.source_document_id = source.id
             AND archive.content_sha256 = source.content_sha256
             AND archive.retrieval_url = source.url
             AND archive.retrieved_at = source.retrieved_at
            LEFT JOIN editorial_cases AS cases ON cases.source_document_id = source.id
            WHERE source.url LIKE 'https://%'
              AND source.publisher IN (
                  'PARLIAMENT', 'DRE', 'TRANSPARENCY_ENTITY', 'BASE_GOV',
                  'COURT_OF_AUDIT', 'EUROPEAN_PARLIAMENT', 'PUBLIC_PROSECUTOR',
                  'COURT', 'SNS', 'MUNICIPALITY', 'OTHER_OFFICIAL'
              )
              AND source.kind <> 'NEWS_ARTICLE'
            {condition}
            GROUP BY source.id
            ORDER BY source.retrieved_at DESC, source.id DESC
            LIMIT ${len(arguments)}
            """,
            *arguments,
        )
        return [
            {
                "id": str(row["id"]),
                "publisher": str(row["publisher"]),
                "kind": str(row["kind"]),
                "title": str(row["title"]),
                "official_identifier": row["official_identifier"],
                "url": str(row["url"]),
                "retrieved_at": _aware(row["retrieved_at"]),
                "published_at": (
                    _aware(row["published_at"]) if row["published_at"] is not None else None
                ),
                "content_sha256": str(row["content_sha256"]),
                "mime_type": row["mime_type"],
                "editorial_case_count": int(row["editorial_case_count"]),
                "archive_attested": True,
            }
            for row in rows
        ]

    async def create_case(
        self,
        *,
        payload: EditorialCaseCreateRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        case, _created = await self._create_initial_case(
            kind=payload.kind,
            subject_type=payload.subject_type,
            subject_id=payload.subject_id,
            source_document_id=payload.source_document_id,
            normalized_data=payload.normalized_data,
            origin=EditorialOrigin.HUMAN,
            created_by_id=actor.staff_id,
            created_by_alias=actor.public_alias,
            submission_rationale=(
                "Proposta criada no circuito privado; ingestão e revisão não constituem publicação."
            ),
            actor=actor,
            idempotent=False,
        )
        return case

    async def create_ingestion_case(
        self,
        *,
        kind: EditorialCaseKind,
        subject_type: str,
        subject_id: str,
        source_document_id: str,
        normalized_data: dict[str, Any],
        origin_alias: str,
        submission_rationale: str,
        actor: StaffSession,
    ) -> tuple[dict[str, object], bool]:
        """Cria uma proposta de ingestão idempotente, autorizada por staff.

        A identidade humana pertence apenas à decisão ``SUBMIT``. O processo e a
        versão mantêm ``created_by_id`` nulo e origem ``INGESTION`` para nunca
        apresentarem a recolha automática como autoria humana.
        """

        return await self._create_initial_case(
            kind=kind,
            subject_type=subject_type,
            subject_id=subject_id,
            source_document_id=source_document_id,
            normalized_data=normalized_data,
            origin=EditorialOrigin.INGESTION,
            created_by_id=None,
            created_by_alias=origin_alias,
            submission_rationale=submission_rationale,
            actor=actor,
            idempotent=True,
        )

    async def create_ai_case(
        self,
        *,
        subject_type: str,
        subject_id: str,
        source_document_id: str,
        normalized_data: dict[str, Any],
        origin_alias: str,
        submission_rationale: str,
        actor: StaffSession,
    ) -> tuple[dict[str, object], bool]:
        """Cria uma proposta de IA privada, imutável e idempotente.

        A pessoa que pediu a geração fica na decisão ``SUBMIT``. O processo e a
        versão mantêm origem ``AI`` e ``created_by_id`` nulo; o modelo nunca é
        apresentado como revisor nem como fonte.
        """

        return await self._create_initial_case(
            kind=EditorialCaseKind.AI_EXPLANATION,
            subject_type=subject_type,
            subject_id=subject_id,
            source_document_id=source_document_id,
            normalized_data=normalized_data,
            origin=EditorialOrigin.AI,
            created_by_id=None,
            created_by_alias=origin_alias,
            submission_rationale=submission_rationale,
            actor=actor,
            idempotent=True,
        )

    async def _create_initial_case(
        self,
        *,
        kind: EditorialCaseKind,
        subject_type: str,
        subject_id: str,
        source_document_id: str,
        normalized_data: dict[str, Any],
        origin: EditorialOrigin,
        created_by_id: str | None,
        created_by_alias: str,
        submission_rationale: str,
        actor: StaffSession,
        idempotent: bool,
    ) -> tuple[dict[str, object], bool]:
        validate_normalized_data(normalized_data)
        if not 3 <= len(created_by_alias.strip()) <= 80:
            raise EditorialConflictError("Identidade de origem editorial inválida")
        if len(submission_rationale.strip()) < 20:
            raise EditorialConflictError("A fundamentação de submissão é demasiado curta")

        case_id = _new_id("editorial_case")
        version_id = _new_id("editorial_version")
        decision_id = _new_id("editorial_decision")
        normalized_json = _canonical_json(normalized_data)
        normalized_sha256 = hashlib.sha256(normalized_json.encode("utf-8")).hexdigest()
        created_at = datetime.now(UTC).replace(tzinfo=None)
        rationale = submission_rationale.strip()
        decision_sha256 = self._decision_sha256(
            decision_id=decision_id,
            case_id=case_id,
            version_id=version_id,
            action=EditorialAction.SUBMIT,
            previous_state=None,
            resulting_state=EditorialState.PENDING,
            case_revision=1,
            rationale=rationale,
            source_confirmed=False,
            actor=actor,
            created_at=created_at,
        )
        case_created = False
        resolved_case_id = case_id
        advisory_key = f"editorial:{kind.value}:{subject_type}:{subject_id}:{source_document_id}"

        try:
            async with self.pool.acquire() as connection, connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    advisory_key,
                )
                source = await connection.fetchrow(
                    """
                    SELECT source.id
                    FROM source_documents AS source
                    WHERE source.id = $1
                      AND EXISTS (
                          SELECT 1
                          FROM source_archive_attestations AS archive
                          WHERE archive.source_document_id = source.id
                            AND archive.content_sha256 = source.content_sha256
                            AND archive.retrieval_url = source.url
                            AND archive.retrieved_at = source.retrieved_at
                      )
                      AND source.url LIKE 'https://%'
                      AND source.publisher IN (
                          'PARLIAMENT', 'DRE', 'TRANSPARENCY_ENTITY', 'BASE_GOV',
                          'COURT_OF_AUDIT', 'EUROPEAN_PARLIAMENT', 'PUBLIC_PROSECUTOR',
                          'COURT', 'SNS', 'MUNICIPALITY', 'OTHER_OFFICIAL'
                      )
                      AND source.kind <> 'NEWS_ARTICLE'
                    FOR SHARE
                    """,
                    source_document_id,
                )
                if source is None:
                    raise EditorialSourceError(
                        "A fonte não existe ou ainda não tem arquivo SHA-256 atestado"
                    )

                existing = await connection.fetchrow(
                    """
                    SELECT c.id, c.origin, v.normalized_sha256
                    FROM editorial_cases AS c
                    LEFT JOIN editorial_versions AS v ON v.id = c.current_version_id
                    WHERE c.kind = $1::"EditorialCaseKind"
                      AND c.subject_type = $2
                      AND c.subject_id = $3
                      AND c.source_document_id = $4
                    """,
                    kind.value,
                    subject_type,
                    subject_id,
                    source_document_id,
                )
                if existing is not None:
                    if (
                        idempotent
                        and str(existing["origin"]) == origin.value
                        and str(existing["normalized_sha256"]) == normalized_sha256
                    ):
                        resolved_case_id = str(existing["id"])
                    else:
                        raise EditorialConflictError(
                            "Já existe um processo para este assunto e esta fonte, ou o conteúdo "
                            "é incompatível"
                        )

                if existing is not None:
                    # A proposta de ingestão repetida é um no-op auditável: não
                    # cria outra versão nem outra decisão.
                    pass
                else:
                    await connection.execute(
                        """
                        INSERT INTO editorial_cases
                            (id, kind, subject_type, subject_id, source_document_id,
                             origin, created_by_id, created_by_alias, current_version_id,
                             current_state, revision, created_at, updated_at)
                        VALUES ($1, $2::"EditorialCaseKind", $3, $4, $5,
                                $6::"EditorialOrigin", $7, $8, NULL, 'PENDING', 0, $9, $9)
                        """,
                        case_id,
                        kind.value,
                        subject_type,
                        subject_id,
                        source_document_id,
                        origin.value,
                        created_by_id,
                        created_by_alias.strip(),
                        created_at,
                    )
                    await connection.execute(
                        """
                        INSERT INTO editorial_versions
                            (id, case_id, version_number, normalized_json,
                             normalized_sha256, previous_version_id, origin,
                             created_by_id, created_by_alias, created_at)
                        VALUES ($1, $2, 1, $3::jsonb, $4, NULL,
                                $5::"EditorialOrigin", $6, $7, $8)
                        """,
                        version_id,
                        case_id,
                        normalized_json,
                        normalized_sha256,
                        origin.value,
                        created_by_id,
                        created_by_alias.strip(),
                        created_at,
                    )
                    await self._insert_decision(
                        connection,
                        decision_id=decision_id,
                        case_id=case_id,
                        version_id=version_id,
                        action=EditorialAction.SUBMIT,
                        previous_state=None,
                        resulting_state=EditorialState.PENDING,
                        case_revision=1,
                        rationale=rationale,
                        source_confirmed=False,
                        actor=actor,
                        decision_sha256=decision_sha256,
                        created_at=created_at,
                    )
                    await connection.execute(
                        """
                        UPDATE editorial_cases
                        SET current_version_id = $2,
                            current_state = 'PENDING',
                            revision = 1,
                            updated_at = $3
                        WHERE id = $1
                        """,
                        case_id,
                        version_id,
                        created_at,
                    )
                    case_created = True
        except asyncpg.UniqueViolationError as exc:
            raise EditorialConflictError(
                "Já existe um processo para este assunto e esta fonte, ou o conteúdo é repetido"
            ) from exc

        return await self.get_case(resolved_case_id), case_created

    async def get_case(self, case_id: str) -> dict[str, object]:
        async with self.pool.acquire() as connection:
            case = await connection.fetchrow(
                """
                SELECT
                    c.id, c.kind, c.subject_type, c.subject_id, c.current_state,
                    c.revision, c.origin, c.created_by_alias, c.created_at, c.updated_at,
                    c.current_version_id,
                    source.id AS source_id,
                    source.publisher AS source_publisher,
                    source.kind AS source_kind,
                    source.title AS source_title,
                    source.official_identifier,
                    source.url AS source_url,
                    source.retrieved_at AS source_retrieved_at,
                    source.published_at AS source_published_at,
                    source.content_sha256 AS source_sha256,
                    source.mime_type AS source_mime_type,
                    archive.storage_backend,
                    archive.byte_size,
                    archive.archived_at,
                    archive.attestation_sha256
                FROM editorial_cases AS c
                JOIN source_documents AS source ON source.id = c.source_document_id
                LEFT JOIN LATERAL (
                    SELECT storage_backend, byte_size, archived_at,
                           attestation_sha256
                    FROM source_archive_attestations
                    WHERE source_document_id = source.id
                      AND content_sha256 = source.content_sha256
                      AND retrieval_url = source.url
                      AND retrieved_at = source.retrieved_at
                    ORDER BY archived_at DESC, id DESC
                    LIMIT 1
                ) AS archive ON TRUE
                WHERE c.id = $1 AND c.current_version_id IS NOT NULL
                """,
                case_id,
            )
            if case is None:
                raise EditorialNotFoundError("Processo editorial não encontrado")
            versions = await connection.fetch(
                """
                SELECT id, version_number, normalized_json, normalized_sha256,
                       previous_version_id, origin, created_by_alias, created_at
                FROM editorial_versions
                WHERE case_id = $1
                ORDER BY version_number DESC
                """,
                case_id,
            )
            decisions = await connection.fetch(
                """
                SELECT id, version_id, action, previous_state, resulting_state,
                       case_revision, rationale, source_confirmed, actor_alias,
                       decision_sha256, created_at
                FROM editorial_decisions
                WHERE case_id = $1
                ORDER BY case_revision DESC
                """,
                case_id,
            )
            publication_events = await connection.fetch(
                """
                SELECT id, version_id, action, target_type, target_id, rationale,
                       actor_alias, event_sha256, created_at
                FROM editorial_publication_events
                WHERE case_id = $1
                ORDER BY created_at DESC, id DESC
                """,
                case_id,
            )

        return {
            "id": str(case["id"]),
            "kind": str(case["kind"]),
            "subject_type": str(case["subject_type"]),
            "subject_id": str(case["subject_id"]),
            "current_state": str(case["current_state"]),
            "revision": int(case["revision"]),
            "origin": str(case["origin"]),
            "created_by_alias": str(case["created_by_alias"]),
            "created_at": _aware(case["created_at"]),
            "updated_at": _aware(case["updated_at"]),
            "current_version_id": str(case["current_version_id"]),
            "source": {
                "id": str(case["source_id"]),
                "publisher": str(case["source_publisher"]),
                "kind": str(case["source_kind"]),
                "title": str(case["source_title"]),
                "official_identifier": case["official_identifier"],
                "url": str(case["source_url"]),
                "retrieved_at": _aware(case["source_retrieved_at"]),
                "published_at": (
                    _aware(case["source_published_at"])
                    if case["source_published_at"] is not None
                    else None
                ),
                "content_sha256": str(case["source_sha256"]),
                "mime_type": case["source_mime_type"],
                "archive": (
                    {
                        "storage_backend": str(case["storage_backend"]),
                        "byte_size": int(case["byte_size"]),
                        "archived_at": _aware(case["archived_at"]),
                        "attestation_sha256": str(case["attestation_sha256"]),
                    }
                    if case["storage_backend"] is not None
                    else None
                ),
            },
            "versions": [
                {
                    "id": str(row["id"]),
                    "version_number": int(row["version_number"]),
                    "normalized_data": _as_json(row["normalized_json"]),
                    "normalized_sha256": str(row["normalized_sha256"]),
                    "previous_version_id": row["previous_version_id"],
                    "origin": str(row["origin"]),
                    "created_by_alias": str(row["created_by_alias"]),
                    "created_at": _aware(row["created_at"]),
                    "is_current": str(row["id"]) == str(case["current_version_id"]),
                }
                for row in versions
            ],
            "decisions": [
                {
                    "id": str(row["id"]),
                    "version_id": str(row["version_id"]),
                    "action": str(row["action"]),
                    "previous_state": (
                        str(row["previous_state"]) if row["previous_state"] is not None else None
                    ),
                    "resulting_state": str(row["resulting_state"]),
                    "case_revision": int(row["case_revision"]),
                    "rationale": str(row["rationale"]),
                    "source_confirmed": bool(row["source_confirmed"]),
                    "actor_alias": str(row["actor_alias"]),
                    "decision_sha256": str(row["decision_sha256"]),
                    "created_at": _aware(row["created_at"]),
                }
                for row in decisions
            ],
            "publication_events": [
                {
                    "id": str(row["id"]),
                    "version_id": str(row["version_id"]),
                    "action": str(row["action"]),
                    "target_type": str(row["target_type"]),
                    "target_id": str(row["target_id"]),
                    "rationale": str(row["rationale"]),
                    "actor_alias": str(row["actor_alias"]),
                    "event_sha256": str(row["event_sha256"]),
                    "created_at": _aware(row["created_at"]),
                }
                for row in publication_events
            ],
            "publishable": False,
            "publication_notice": (
                "A aprovação permanece privada. Não existe publicação genérica: cada domínio "
                "exige um adaptador próprio, nova confirmação humana e um evento imutável."
            ),
        }

    async def transition(
        self,
        *,
        case_id: str,
        action: EditorialAction,
        expected_revision: int,
        rationale: str,
        source_confirmed: bool,
        actor: StaffSession,
    ) -> dict[str, object]:
        transitions = {
            EditorialAction.START_REVIEW: (EditorialState.PENDING, EditorialState.IN_REVIEW),
            EditorialAction.APPROVE: (EditorialState.IN_REVIEW, EditorialState.APPROVED),
            EditorialAction.REJECT: (EditorialState.IN_REVIEW, EditorialState.REJECTED),
        }
        if action not in transitions:
            raise EditorialConflictError("Ação editorial não disponível neste circuito")
        required_state, resulting_state = transitions[action]
        decision_id = _new_id("editorial_decision")
        created_at = datetime.now(UTC).replace(tzinfo=None)

        async with self.pool.acquire() as connection, connection.transaction():
            case = await self._locked_case(connection, case_id)
            previous_state = EditorialState(str(case["current_state"]))
            revision = int(case["revision"])
            if revision != expected_revision:
                raise EditorialConflictError(
                    "O processo foi alterado por outra decisão; atualize antes de continuar"
                )
            if previous_state != required_state:
                raise EditorialConflictError(
                    f"A ação {action.value} não é válida no estado {previous_state.value}"
                )
            if action is EditorialAction.APPROVE and not source_confirmed:
                raise EditorialConflictError("A aprovação exige confirmação humana da fonte")
            if action is not EditorialAction.APPROVE and source_confirmed:
                raise EditorialConflictError("Esta decisão não aceita confirmação de aprovação")

            next_revision = revision + 1
            version_id = str(case["current_version_id"])
            digest = self._decision_sha256(
                decision_id=decision_id,
                case_id=case_id,
                version_id=version_id,
                action=action,
                previous_state=previous_state,
                resulting_state=resulting_state,
                case_revision=next_revision,
                rationale=rationale,
                source_confirmed=source_confirmed,
                actor=actor,
                created_at=created_at,
            )
            await self._insert_decision(
                connection,
                decision_id=decision_id,
                case_id=case_id,
                version_id=version_id,
                action=action,
                previous_state=previous_state,
                resulting_state=resulting_state,
                case_revision=next_revision,
                rationale=rationale,
                source_confirmed=source_confirmed,
                actor=actor,
                decision_sha256=digest,
                created_at=created_at,
            )
            await connection.execute(
                """
                UPDATE editorial_cases
                SET current_state = $2::"EditorialState",
                    revision = $3,
                    updated_at = $4
                WHERE id = $1
                """,
                case_id,
                resulting_state.value,
                next_revision,
                created_at,
            )
        return await self.get_case(case_id)

    async def regenerate_ai_case(
        self,
        *,
        case_id: str,
        expected_revision: int,
        expected_current_version_sha256: str,
        normalized_data: dict[str, Any],
        origin_alias: str,
        rationale: str,
        actor: StaffSession,
    ) -> dict[str, object]:
        """Acrescenta uma versão AI e atribui a decisão CORRECT ao humano que a pediu."""

        validate_normalized_data(normalized_data)
        clean_alias = origin_alias.strip()
        clean_rationale = rationale.strip()
        if not 3 <= len(clean_alias) <= 80:
            raise EditorialConflictError("Identidade de origem editorial inválida")
        if len(clean_rationale) < 20:
            raise EditorialConflictError("A fundamentação de regeneração é demasiado curta")

        version_id = _new_id("editorial_version")
        decision_id = _new_id("editorial_decision")
        normalized_json = _canonical_json(normalized_data)
        normalized_sha256 = hashlib.sha256(normalized_json.encode("utf-8")).hexdigest()
        created_at = datetime.now(UTC).replace(tzinfo=None)

        try:
            async with self.pool.acquire() as connection, connection.transaction():
                case = await connection.fetchrow(
                    """
                    SELECT c.id, c.kind, c.subject_type, c.origin, c.current_version_id,
                           c.current_state, c.revision, version.version_number,
                           version.normalized_sha256
                    FROM editorial_cases c
                    JOIN editorial_versions version ON version.id = c.current_version_id
                    WHERE c.id = $1
                    FOR UPDATE OF c
                    """,
                    case_id,
                )
                if case is None:
                    raise EditorialNotFoundError("Processo editorial não encontrado")
                if (
                    str(case["kind"]) != EditorialCaseKind.AI_EXPLANATION.value
                    or str(case["subject_type"]) != "DRE_DOCUMENT_SNAPSHOT"
                    or str(case["origin"]) != EditorialOrigin.AI.value
                ):
                    raise EditorialConflictError(
                        "O processo não pertence ao circuito editorial DRE de IA"
                    )
                previous_state = EditorialState(str(case["current_state"]))
                revision = int(case["revision"])
                if revision != expected_revision:
                    raise EditorialConflictError(
                        "O processo foi alterado por outra decisão; atualize antes de continuar"
                    )
                if previous_state not in {
                    EditorialState.IN_REVIEW,
                    EditorialState.APPROVED,
                    EditorialState.REJECTED,
                    EditorialState.WITHDRAWN,
                }:
                    raise EditorialConflictError(
                        "Inicie a revisão humana antes de pedir uma nova versão de IA"
                    )
                if str(case["normalized_sha256"]) != expected_current_version_sha256:
                    raise EditorialConflictError(
                        "A versão comparada já não é a atual; atualize antes de continuar"
                    )
                if str(case["normalized_sha256"]) == normalized_sha256:
                    raise EditorialConflictError("A nova geração não altera a proposta atual")

                await connection.execute(
                    """
                    INSERT INTO editorial_versions
                        (id, case_id, version_number, normalized_json,
                         normalized_sha256, previous_version_id, origin,
                         created_by_id, created_by_alias, created_at)
                    VALUES ($1, $2, $3, $4::jsonb, $5, $6,
                            'AI', NULL, $7, $8)
                    """,
                    version_id,
                    case_id,
                    int(case["version_number"]) + 1,
                    normalized_json,
                    normalized_sha256,
                    case["current_version_id"],
                    clean_alias,
                    created_at,
                )
                next_revision = revision + 1
                digest = self._decision_sha256(
                    decision_id=decision_id,
                    case_id=case_id,
                    version_id=version_id,
                    action=EditorialAction.CORRECT,
                    previous_state=previous_state,
                    resulting_state=EditorialState.PENDING,
                    case_revision=next_revision,
                    rationale=clean_rationale,
                    source_confirmed=False,
                    actor=actor,
                    created_at=created_at,
                )
                await self._insert_decision(
                    connection,
                    decision_id=decision_id,
                    case_id=case_id,
                    version_id=version_id,
                    action=EditorialAction.CORRECT,
                    previous_state=previous_state,
                    resulting_state=EditorialState.PENDING,
                    case_revision=next_revision,
                    rationale=clean_rationale,
                    source_confirmed=False,
                    actor=actor,
                    decision_sha256=digest,
                    created_at=created_at,
                )
                await connection.execute(
                    """
                    UPDATE editorial_cases
                    SET current_version_id = $2,
                        current_state = 'PENDING',
                        revision = $3,
                        updated_at = $4
                    WHERE id = $1
                    """,
                    case_id,
                    version_id,
                    next_revision,
                    created_at,
                )
        except asyncpg.UniqueViolationError as exc:
            raise EditorialConflictError("A nova versão de IA já existe no histórico") from exc
        return await self.get_case(case_id)

    async def correct_case(
        self,
        *,
        case_id: str,
        payload: EditorialCorrectionRequest,
        actor: StaffSession,
    ) -> dict[str, object]:
        version_id = _new_id("editorial_version")
        decision_id = _new_id("editorial_decision")
        normalized_json = _canonical_json(payload.normalized_data)
        normalized_sha256 = hashlib.sha256(normalized_json.encode("utf-8")).hexdigest()
        created_at = datetime.now(UTC).replace(tzinfo=None)

        try:
            async with self.pool.acquire() as connection, connection.transaction():
                case = await self._locked_case(connection, case_id)
                previous_state = EditorialState(str(case["current_state"]))
                revision = int(case["revision"])
                if revision != payload.expected_revision:
                    raise EditorialConflictError(
                        "O processo foi alterado por outra decisão; atualize antes de continuar"
                    )
                if previous_state not in {
                    EditorialState.IN_REVIEW,
                    EditorialState.APPROVED,
                    EditorialState.REJECTED,
                    EditorialState.WITHDRAWN,
                }:
                    raise EditorialConflictError(
                        f"O estado {previous_state.value} não admite correção"
                    )
                current_version = await connection.fetchrow(
                    """
                    SELECT version_number, normalized_sha256
                    FROM editorial_versions
                    WHERE id = $1 AND case_id = $2
                    """,
                    case["current_version_id"],
                    case_id,
                )
                if current_version is None:
                    raise EditorialConflictError("A versão atual não foi encontrada")
                if str(current_version["normalized_sha256"]) == normalized_sha256:
                    raise EditorialConflictError("A correção não altera os dados normalizados")

                await connection.execute(
                    """
                    INSERT INTO editorial_versions
                        (id, case_id, version_number, normalized_json,
                         normalized_sha256, previous_version_id, origin,
                         created_by_id, created_by_alias, created_at)
                    VALUES ($1, $2, $3, $4::jsonb, $5, $6,
                            'HUMAN', $7, $8, $9)
                    """,
                    version_id,
                    case_id,
                    int(current_version["version_number"]) + 1,
                    normalized_json,
                    normalized_sha256,
                    case["current_version_id"],
                    actor.staff_id,
                    actor.public_alias,
                    created_at,
                )
                next_revision = revision + 1
                digest = self._decision_sha256(
                    decision_id=decision_id,
                    case_id=case_id,
                    version_id=version_id,
                    action=EditorialAction.CORRECT,
                    previous_state=previous_state,
                    resulting_state=EditorialState.PENDING,
                    case_revision=next_revision,
                    rationale=payload.rationale,
                    source_confirmed=False,
                    actor=actor,
                    created_at=created_at,
                )
                await self._insert_decision(
                    connection,
                    decision_id=decision_id,
                    case_id=case_id,
                    version_id=version_id,
                    action=EditorialAction.CORRECT,
                    previous_state=previous_state,
                    resulting_state=EditorialState.PENDING,
                    case_revision=next_revision,
                    rationale=payload.rationale,
                    source_confirmed=False,
                    actor=actor,
                    decision_sha256=digest,
                    created_at=created_at,
                )
                await connection.execute(
                    """
                    UPDATE editorial_cases
                    SET current_version_id = $2,
                        current_state = 'PENDING',
                        revision = $3,
                        updated_at = $4
                    WHERE id = $1
                    """,
                    case_id,
                    version_id,
                    next_revision,
                    created_at,
                )
        except asyncpg.UniqueViolationError as exc:
            raise EditorialConflictError("A correção já existe no histórico") from exc
        return await self.get_case(case_id)

    @staticmethod
    async def _locked_case(
        connection: asyncpg.Connection,
        case_id: str,
    ) -> asyncpg.Record:
        row = await connection.fetchrow(
            """
            SELECT id, current_version_id, current_state, revision
            FROM editorial_cases
            WHERE id = $1
            FOR UPDATE
            """,
            case_id,
        )
        if row is None:
            raise EditorialNotFoundError("Processo editorial não encontrado")
        return row

    @staticmethod
    async def _insert_decision(
        connection: asyncpg.Connection,
        *,
        decision_id: str,
        case_id: str,
        version_id: str,
        action: EditorialAction,
        previous_state: EditorialState | None,
        resulting_state: EditorialState,
        case_revision: int,
        rationale: str,
        source_confirmed: bool,
        actor: StaffSession,
        decision_sha256: str,
        created_at: datetime,
    ) -> None:
        await connection.execute(
            """
            INSERT INTO editorial_decisions
                (id, case_id, version_id, action, previous_state, resulting_state,
                 case_revision, rationale, source_confirmed, actor_id, actor_alias,
                 decision_sha256, created_at)
            VALUES ($1, $2, $3, $4::"EditorialDecisionAction",
                    $5::"EditorialState", $6::"EditorialState", $7, $8, $9,
                    $10, $11, $12, $13)
            """,
            decision_id,
            case_id,
            version_id,
            action.value,
            previous_state.value if previous_state is not None else None,
            resulting_state.value,
            case_revision,
            rationale,
            source_confirmed,
            actor.staff_id,
            actor.public_alias,
            decision_sha256,
            created_at,
        )

    @staticmethod
    def _decision_sha256(
        *,
        decision_id: str,
        case_id: str,
        version_id: str,
        action: EditorialAction,
        previous_state: EditorialState | None,
        resulting_state: EditorialState,
        case_revision: int,
        rationale: str,
        source_confirmed: bool,
        actor: StaffSession,
        created_at: datetime,
    ) -> str:
        return _sha256_json(
            {
                "id": decision_id,
                "case_id": case_id,
                "version_id": version_id,
                "action": action.value,
                "previous_state": previous_state.value if previous_state is not None else None,
                "resulting_state": resulting_state.value,
                "case_revision": case_revision,
                "rationale": rationale,
                "source_confirmed": source_confirmed,
                "actor_id": actor.staff_id,
                "actor_alias": actor.public_alias,
                "created_at": created_at.isoformat(timespec="milliseconds") + "Z",
            }
        )

    @staticmethod
    def _case_summary(row: asyncpg.Record) -> dict[str, object]:
        return {
            "id": str(row["id"]),
            "kind": str(row["kind"]),
            "subject_type": str(row["subject_type"]),
            "subject_id": str(row["subject_id"]),
            "current_state": str(row["current_state"]),
            "revision": int(row["revision"]),
            "origin": str(row["origin"]),
            "created_by_alias": str(row["created_by_alias"]),
            "created_at": _aware(row["created_at"]),
            "updated_at": _aware(row["updated_at"]),
            "version_number": int(row["version_number"]),
            "normalized_sha256": str(row["normalized_sha256"]),
            "source": {
                "title": str(row["source_title"]),
                "publisher": str(row["source_publisher"]),
                "url": str(row["source_url"]),
                "retrieved_at": _aware(row["source_retrieved_at"]),
                "content_sha256": str(row["source_sha256"]),
            },
        }
