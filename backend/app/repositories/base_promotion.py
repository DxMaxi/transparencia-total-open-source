"""Compatibilidade segura para a antiga promoção BASE da V4.

A V5 fechou este caminho porque criava contratos, organizações e nós de grafo
antes de existir uma decisão editorial específica. As assinaturas permanecem
temporariamente para que qualquer chamada antiga falhe de forma explícita.
"""

from typing import Any

import asyncpg

_SPECIFIC_GATE_MESSAGE = (
    "A promoção BASE genérica foi desativada; use a porta editorial específica "
    "de contratos BASE, que cria apenas um processo privado PENDING."
)


class BasePromotionRepositoryMixin:
    """Bloqueia materialização e publicação pela porta legada."""

    pool: asyncpg.Pool | None

    async def mark_base_batch_publication_eligible(
        self,
        *,
        batch_id: str,
        reviewed_by: str,
        eligible: bool = True,
    ) -> dict[str, Any]:
        del batch_id, reviewed_by, eligible
        raise ValueError(_SPECIFIC_GATE_MESSAGE)

    async def propose_base_contract_for_review(
        self,
        *,
        contract_snapshot_id: str,
        reviewer_alias: str,
    ) -> dict[str, Any]:
        del contract_snapshot_id, reviewer_alias
        raise ValueError(_SPECIFIC_GATE_MESSAGE)
