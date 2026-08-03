import re
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, field_validator

_PROTECTED_IDENTIFIER_SEQUENCE = re.compile(r"(?<!\d)\d(?:[\W_]*\d){8}(?!\d)")
_INTERNAL_PERSON_ID = re.compile(r"[A-Za-z][A-Za-z0-9:_-]{1,127}")
_CANONICAL_UUID = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _contains_protected_identifier(value: str) -> bool:
    return _PROTECTED_IDENTIFIER_SEQUENCE.search(value) is not None


class SourcePublisher(StrEnum):
    PARLIAMENT = "AR"
    DRE = "DRE"
    TRANSPARENCY_ENTITY = "EPT"
    BASE_GOV = "BASE"
    COURT_OF_AUDIT = "TCONTAS"
    EUROPEAN_PARLIAMENT = "PE"
    PUBLIC_PROSECUTOR = "MP"
    COURT = "TRIBUNAL"
    MEDIA = "MEDIA"
    SNS = "SNS"
    MUNICIPALITY = "MUNICIPIO"
    OTHER_OFFICIAL = "OFICIAL"


class OfficialSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    publisher: SourcePublisher
    label: str
    url: HttpUrl
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content_sha256: str | None = None


class Deputy(BaseModel):
    source_id: str
    parliamentary_name: str
    full_name: str | None = None
    party_short: str | None = None
    constituency: str | None = None
    legislature: str
    email: str | None = None
    source: OfficialSource


class VoteChoice(StrEnum):
    FAVOR = "FAVOR"
    AGAINST = "AGAINST"
    ABSTENTION = "ABSTENTION"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"


class VoteActorType(StrEnum):
    PERSON = "PERSON"
    PARTY = "PARTY"
    UNKNOWN = "UNKNOWN"


class VoteRecord(BaseModel):
    actor_label: str
    actor_source_id: str | None = None
    actor_type: VoteActorType = VoteActorType.UNKNOWN
    choice: VoteChoice


class VoteEvent(BaseModel):
    source_id: str
    title: str
    voted_at: datetime | None = None
    result: str | None = None
    initiative_number: str | None = None
    is_nominal: bool = False
    records: list[VoteRecord] = Field(default_factory=list)
    source: OfficialSource


class ParliamentDataset(BaseModel):
    legislature: str
    dataset_url: HttpUrl
    document_sha256: str
    deputies: list[Deputy] = Field(default_factory=list)
    votes: list[VoteEvent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TransparencyResource(BaseModel):
    title: str
    url: HttpUrl
    category: str
    source: OfficialSource


class LegalDocument(BaseModel):
    title: str
    source_url: HttpUrl
    official_identifier: str | None = None
    published_at: datetime | None = None
    text: str = Field(min_length=1)
    content_sha256: str


class GlossaryItem(BaseModel):
    term: str
    explanation: str


class SourceAnchor(BaseModel):
    section: str
    reason: str


class CitizenSummary(BaseModel):
    title: str
    summary_2_minutes: str
    what_changes: list[str]
    who_is_affected: list[str]
    dates_and_deadlines: list[str]
    duties_and_rights: list[str]
    uncertainties: list[str]
    glossary: list[GlossaryItem]
    source_anchors: list[SourceAnchor]

    @field_validator(
        "what_changes",
        "who_is_affected",
        "dates_and_deadlines",
        "duties_and_rights",
        "uncertainties",
    )
    @classmethod
    def cap_lists(cls, value: list[str]) -> list[str]:
        return value[:12]


class SummaryRequest(BaseModel):
    source_url: HttpUrl


class SummaryResponse(BaseModel):
    summary: CitizenSummary
    source: OfficialSource
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    provider: str
    model: str
    prompt_sha256: str
    source_characters: int
    processed_characters: int
    source_truncated: bool
    requires_human_review: bool = True
    warning: str = (
        "Resumo gerado automaticamente. Não substitui o diploma nem aconselhamento jurídico."
    )


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=512)
    auth: str = Field(min_length=8, max_length=256)


class BrowserPushSubscription(BaseModel):
    endpoint: HttpUrl
    expirationTime: int | None = None
    keys: PushSubscriptionKeys


class PushSubscriptionRequest(BaseModel):
    subscription: BrowserPushSubscription
    districts: list[str] = Field(default_factory=list, max_length=20)
    municipalities: list[str] = Field(default_factory=list, max_length=50)


class PushSubscriptionResponse(BaseModel):
    accepted: bool
    id: str


class PushBroadcastRequest(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=220)
    url: str = Field(default="/", min_length=1, max_length=1024)
    tag: str = Field(default="transparencia-total-update", pattern=r"^[a-z0-9-]{1,80}$")
    district: str | None = Field(default=None, max_length=100)
    municipality: str | None = Field(default=None, max_length=100)

    @field_validator("url")
    @classmethod
    def same_origin_path(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("O destino push deve ser um caminho da própria aplicação")
        if "\\" in value or any(ord(character) < 32 for character in value):
            raise ValueError("O caminho da notificação contém caracteres inválidos")
        return value


class PushBroadcastResponse(BaseModel):
    selected: int
    sent: int
    failed: int


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.3.0"
    environment: str
    database_configured: bool
    ai_provider: str


class ContractPartyRole(StrEnum):
    CONTRACTING_AUTHORITY = "CONTRACTING_AUTHORITY"
    CONTRACTOR = "CONTRACTOR"
    CO_CONTRACTOR = "CO_CONTRACTOR"


class PublicContractProcedure(StrEnum):
    DIRECT_AWARD = "DIRECT_AWARD"
    PRIOR_CONSULTATION = "PRIOR_CONSULTATION"
    PUBLIC_TENDER = "PUBLIC_TENDER"
    LIMITED_TENDER = "LIMITED_TENDER"
    NEGOTIATED_PROCEDURE = "NEGOTIATED_PROCEDURE"
    FRAMEWORK_AGREEMENT = "FRAMEWORK_AGREEMENT"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class BaseDatasetResource(BaseModel):
    title: str
    format: str
    url: HttpUrl
    year: int | None = None


class PublicContractParty(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    name: str = Field(min_length=1, max_length=500)
    # HMAC usado apenas no cruzamento interno; nunca serializado em respostas ou ficheiros.
    protected_identifier_digest: SecretStr | None = Field(
        default=None,
        exclude=True,
        repr=False,
    )
    role: ContractPartyRole

    @field_validator("protected_identifier_digest")
    @classmethod
    def validate_identifier_digest(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not re.fullmatch(r"[0-9a-f]{64}", value.get_secret_value()):
            raise ValueError("O digest protegido deve ser um HMAC-SHA-256 hexadecimal")
        return value


class PublicContractRecord(BaseModel):
    source_id: str
    object: str
    procedure: PublicContractProcedure = PublicContractProcedure.UNKNOWN
    cpv_code: str | None = None
    base_value: Decimal | None = None
    contract_value: Decimal | None = None
    currency: str = "EUR"
    decision_at: datetime | None = None
    signed_at: datetime | None = None
    published_at: datetime | None = None
    execution_days: int | None = None
    contracting_authorities: list[PublicContractParty] = Field(default_factory=list)
    contractors: list[PublicContractParty] = Field(default_factory=list)
    source: OfficialSource
    direct_official_url: HttpUrl | None = None


class BaseContractCollection(BaseModel):
    dataset_resource: BaseDatasetResource
    document_sha256: str
    contracts: list[PublicContractRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ActorAssociationKey(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    organisation_name: str = Field(min_length=2, max_length=500)
    protected_nipc_digest: SecretStr | None = Field(default=None, repr=False, exclude=True)
    official_evidence_url: HttpUrl

    @field_validator("organisation_name")
    @classmethod
    def reject_identifier_in_organisation_name(cls, value: str) -> str:
        if _contains_protected_identifier(value):
            raise ValueError("A designação pública não pode conter um identificador fiscal")
        return value

    @field_validator("protected_nipc_digest")
    @classmethod
    def validate_nipc_digest(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not re.fullmatch(r"[0-9a-f]{64}", value.get_secret_value()):
            raise ValueError("O digest protegido deve ser um HMAC-SHA-256 hexadecimal")
        return value


class PublicActorMatchKey(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    person_id: str = Field(min_length=2, max_length=128)
    public_name: str = Field(min_length=2, max_length=300)
    public_role: Literal[
        "DEPUTY",
        "MINISTER",
        "SECRETARY_OF_STATE",
        "MAYOR",
        "OTHER_PUBLIC_OFFICE",
    ]
    official_role_source_url: HttpUrl
    protected_nif_digest: SecretStr | None = Field(default=None, repr=False, exclude=True)
    official_associations: list[ActorAssociationKey] = Field(default_factory=list, max_length=100)

    @field_validator("person_id")
    @classmethod
    def validate_internal_person_id(cls, value: str) -> str:
        if not (_INTERNAL_PERSON_ID.fullmatch(value) or _CANONICAL_UUID.fullmatch(value)):
            raise ValueError("O identificador interno da pessoa tem formato inválido")
        return value

    @field_validator("public_name")
    @classmethod
    def reject_identifier_in_public_actor_name(cls, value: str) -> str:
        if _contains_protected_identifier(value):
            raise ValueError("O nome público não pode conter um identificador fiscal")
        return value

    @field_validator("protected_nif_digest")
    @classmethod
    def validate_nif_digest(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not re.fullmatch(r"[0-9a-f]{64}", value.get_secret_value()):
            raise ValueError("O digest protegido deve ser um HMAC-SHA-256 hexadecimal")
        return value


class ContractMatchMethod(StrEnum):
    EXACT_PROTECTED_IDENTIFIER = "EXACT_PROTECTED_IDENTIFIER"
    EXACT_PUBLIC_ORGANISATION_ID = "EXACT_PUBLIC_ORGANISATION_ID"
    NORMALISED_NAME = "NORMALISED_NAME"


class ContractMatchCandidate(BaseModel):
    contract_source_id: str
    person_id: str
    public_name: str
    matched_party_name: str
    party_role: ContractPartyRole
    method: ContractMatchMethod
    score: Decimal
    contract_source_url: HttpUrl
    contract_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_source_retrieved_at: datetime
    contract_direct_official_url: HttpUrl | None = None
    actor_source_url: HttpUrl
    association_evidence_url: HttpUrl | None = None
    decision: Literal["PENDING_REVIEW"] = "PENDING_REVIEW"
    warning: str = (
        "Correspondência técnica para revisão humana; não constitui prova de conflito, "
        "ilicitude ou benefício indevido."
    )


class RightOfReplyRequest(BaseModel):
    target_type: str = Field(pattern=r"^[A-Z_]{2,64}$")
    target_id: str = Field(min_length=1, max_length=128)
    original_record_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    claimant_public_name: str = Field(min_length=2, max_length=200)
    claimant_role: str = Field(min_length=2, max_length=200)
    statement_text: str = Field(min_length=20, max_length=10_000)
    official_response_url: HttpUrl | None = None


class RightOfReplyReceipt(BaseModel):
    public_reference: str
    target_type: str
    target_id: str
    statement_sha256: str
    audit_sha256: str
    submitted_at: datetime
    status: Literal["RECEIVED"] = "RECEIVED"
    notice: str = (
        "Recebido para verificação de identidade e prova. A submissão não é publicada "
        "automaticamente nem altera o registo original."
    )


class GenericCitizenProfile(BaseModel):
    irs_bracket: Literal["isento", "baixo", "medio", "alto", "nao_indicar"]
    district: str = Field(min_length=2, max_length=100)
    children: int = Field(default=0, ge=0, le=20)
    dependants: int = Field(default=0, ge=0, le=20)
    employment_status: Literal[
        "trabalhador_conta_outrem",
        "independente",
        "reformado",
        "desempregado",
        "nao_indicar",
    ]


class VerifiedImpactFact(BaseModel):
    fact_id: str = Field(pattern=r"^[A-Z0-9._-]{2,80}$")
    title: str
    deterministic_result: str
    effective_date: str
    official_source_url: HttpUrl
    source_anchor: str
    caveats: list[str] = Field(default_factory=list, max_length=12)


class CitizenImpactExplanation(BaseModel):
    fact_id: str
    plain_language: str
    practical_effect: str
    effective_date: str
    source_anchor: str


class CitizenGuideExplanation(BaseModel):
    title: str
    summary: str
    impacts: list[CitizenImpactExplanation]
    not_applicable: list[str]
    missing_information: list[str]
    uncertainties: list[str]
    cited_fact_ids: list[str]
    requires_human_review: bool = True


class CitizenGuideRequest(BaseModel):
    profile: GenericCitizenProfile
    verified_facts: list[VerifiedImpactFact] = Field(min_length=1, max_length=50)


class CitizenGuideResponse(BaseModel):
    explanation: CitizenGuideExplanation
    provider: str
    model: str
    prompt_version: str
    prompt_sha256: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    requires_human_review: bool = True
    warning: str = (
        "Explicação automática baseada apenas nos factos fornecidos; não substitui "
        "aconselhamento jurídico, fiscal ou financeiro."
    )


class PublicDataMode(StrEnum):
    LIVE = "LIVE"
    EMPTY = "EMPTY"
    UNAVAILABLE = "UNAVAILABLE"


class PublicRecordCounts(BaseModel):
    politicians: int = 0
    promises: int = 0
    contracts: int = 0
    relationships: int = 0
    news: int = 0
    citizen_alerts: int = 0


class SourceSyncState(BaseModel):
    source_name: str
    status: Literal["NEVER", "RUNNING", "SUCCEEDED", "PARTIAL", "FAILED"]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    records_read: int = 0
    records_written: int = 0
    warning_count: int = 0
    dataset_url: HttpUrl | None = None
    code_version: str | None = None


class PublicDataStatus(BaseModel):
    mode: PublicDataMode
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    database_configured: bool
    counts: PublicRecordCounts
    sources: list[SourceSyncState]
    message: str
    publication_rule: str = (
        "A API pública devolve apenas registos que cumpram as regras explícitas de "
        "verificação, revisão humana e publicação de cada conjunto de dados."
    )


class PublishedPersonSummary(BaseModel):
    id: str
    slug: str
    name: str
    role: str
    party: str
    party_short: str
    constituency: str
    legislature: str
    portrait_url: HttpUrl | None = None
    verified_at: datetime
    profile_source: OfficialSource


class PublishedVote(BaseModel):
    id: str
    title: str
    date: datetime | None = None
    choice: VoteChoice
    result: str
    initiative_number: str
    source: OfficialSource
    is_nominal: bool = True


class PublishedPoliticianProfile(PublishedPersonSummary):
    attendance_rate: int | None = Field(default=None, ge=0, le=100)
    attendance_label: str
    nominal_votes_available: bool
    nominal_vote_count: int = Field(ge=0)
    declaration_source: OfficialSource
    votes: list[PublishedVote] = Field(default_factory=list)


class PublishedPromiseEvidence(BaseModel):
    id: str
    legal_reference: str
    summary: str
    source: OfficialSource
    published_at: datetime | None = None


class PublishedPromise(BaseModel):
    id: str
    title: str
    area: str
    status: Literal["FULFILLED", "IN_PROGRESS", "BROKEN", "ABANDONED"]
    progress: int = Field(ge=0, le=100)
    programme_page: str
    programme_source: OfficialSource
    rationale: str
    last_reviewed_at: datetime
    evidence: list[PublishedPromiseEvidence] = Field(min_length=1)


class PublishedInterestNode(BaseModel):
    id: str
    label: str
    subtitle: str
    kind: Literal["person", "public", "company", "party", "other"]
    verified: Literal[True] = True


class PublishedInterestEdge(BaseModel):
    id: str
    source_id: str
    target_id: str
    label: str
    period: str
    review_state: Literal["Revisto"] = "Revisto"
    source: OfficialSource
    year: int | None = None
    party: str | None = None
    amount: Decimal | None = None
    company: str | None = None


class PublishedStatement(BaseModel):
    quote: str
    speaker: str
    stated_at: datetime | None = None
    source: OfficialSource


class PublishedComparisonVote(BaseModel):
    choice: VoteChoice
    initiative: str
    voted_at: datetime | None = None
    source: OfficialSource


class PublishedComparisonMetrics(BaseModel):
    outcome: Literal["CONSISTENT", "INCONSISTENT", "INCONCLUSIVE"]
    score: Decimal | None = Field(default=None, ge=0, le=100)
    comparable_pairs: int = Field(ge=1)
    total_statements: int = Field(ge=1)
    methodology_version: str
    rationale: str


class PublishedComparison(BaseModel):
    id: str
    subject: str
    statement: PublishedStatement
    vote: PublishedComparisonVote
    comparison: PublishedComparisonMetrics


class PublicInvestigatorDataset(BaseModel):
    nodes: list[PublishedInterestNode] = Field(default_factory=list)
    edges: list[PublishedInterestEdge] = Field(default_factory=list)
    comparisons: list[PublishedComparison] = Field(default_factory=list)
