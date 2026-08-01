from dataclasses import dataclass

from app.core.security import is_official_url
from app.models.api import PublicActorMatchKey

PUBLIC_OFFICE_ROLES = frozenset(
    {
        "DEPUTY",
        "MINISTER",
        "SECRETARY_OF_STATE",
        "MAYOR",
        "OTHER_PUBLIC_OFFICE",
    }
)


@dataclass(frozen=True, slots=True)
class IndexingDecision:
    allowed: bool
    reason: str
    requires_human_review: bool = True


def assess_public_actor(actor: PublicActorMatchKey) -> IndexingDecision:
    """Aplica o limite mínimo de relevância pública antes de qualquer cruzamento.

    Ser PEP ou titular de cargo público nunca é apresentado como indício de ilícito.
    A função apenas decide se existe base suficiente para criar uma correspondência
    técnica, sempre pendente de revisão humana.
    """

    if actor.public_role not in PUBLIC_OFFICE_ROLES:
        return IndexingDecision(False, "O cargo não está na lista pública de titulares elegíveis")
    if not is_official_url(str(actor.official_role_source_url)):
        return IndexingDecision(False, "O exercício do cargo não tem fonte oficial autorizada")
    return IndexingDecision(
        True,
        "Titular de cargo público com fonte oficial; cruzamento limitado à função pública",
    )


def association_has_public_evidence(url: str) -> bool:
    """Relações empresariais só entram no índice quando a prova é oficial."""

    return is_official_url(url)


def may_auto_publish_relationship(*, verified: bool, reviewed: bool) -> bool:
    """Nenhuma ligação sensível é publicada apenas pelo resultado de um algoritmo."""

    return verified and reviewed
