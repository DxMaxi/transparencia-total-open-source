import httpx
from fastapi import APIRouter, HTTPException
from openai import APIError

from app.core.config import get_settings
from app.models.api import (
    CitizenGuideRequest,
    CitizenGuideResponse,
    OfficialSource,
    SourcePublisher,
    SummaryRequest,
    SummaryResponse,
)
from app.services.ai_summarizer import PROMPT_SHA256, get_summarizer
from app.services.civic_guide import (
    CIVIC_GUIDE_PROMPT_SHA256,
    CIVIC_GUIDE_PROMPT_VERSION,
    get_civic_guide,
)
from app.services.dre import DreCollector
from app.services.http import OfficialHttpClient

router = APIRouter(prefix="/ai", tags=["IA — resumos cidadãos"])


@router.post("/summaries", response_model=SummaryResponse)
async def summarize(request: SummaryRequest) -> SummaryResponse:
    settings = get_settings()
    if settings.ai_provider == "disabled":
        raise HTTPException(status_code=503, detail="Pipeline de IA desativado")
    try:
        async with OfficialHttpClient(settings) as http:
            document = await DreCollector(settings, http).fetch_document(str(request.source_url))
        summarizer = get_summarizer(settings)
        summary = await summarizer.summarize(document)
        return SummaryResponse(
            summary=summary,
            source=OfficialSource(
                publisher=SourcePublisher.DRE,
                label=document.official_identifier or document.title,
                url=document.source_url,
                content_sha256=document.content_sha256,
            ),
            provider=settings.ai_provider,
            model=settings.openai_model,
            prompt_sha256=PROMPT_SHA256,
            source_characters=len(document.text),
            processed_characters=min(len(document.text), settings.ai_max_source_chars),
            source_truncated=len(document.text) > settings.ai_max_source_chars,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Falha ao obter o diploma oficial") from exc
    except APIError as exc:
        raise HTTPException(status_code=502, detail="Falha temporária no fornecedor de IA") from exc


@router.post("/civic-guide", response_model=CitizenGuideResponse)
async def civic_guide(request: CitizenGuideRequest) -> CitizenGuideResponse:
    settings = get_settings()
    if settings.ai_provider == "disabled":
        raise HTTPException(status_code=503, detail="Pipeline de IA desativado")
    try:
        explanation = await get_civic_guide(settings).explain(
            request.profile,
            request.verified_facts,
        )
        return CitizenGuideResponse(
            explanation=explanation,
            provider=settings.ai_provider,
            model=settings.openai_model,
            prompt_version=CIVIC_GUIDE_PROMPT_VERSION,
            prompt_sha256=CIVIC_GUIDE_PROMPT_SHA256,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except APIError as exc:
        raise HTTPException(status_code=502, detail="Falha temporária no fornecedor de IA") from exc
