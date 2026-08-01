import csv
import io
import json
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.dependencies import get_repository
from app.core.config import get_settings
from app.repositories.postgres import PostgresRepository

OpenDataset = Literal[
    "contracts",
    "interest-graph",
    "news",
    "citizen-alerts",
    "rights-of-reply",
]

router = APIRouter(prefix="/open-data", tags=["Open Data"])


async def _rows(
    dataset: OpenDataset,
    repository: PostgresRepository,
    limit: int,
    offset: int,
) -> list[dict[str, object]]:
    if not repository.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Open Data indisponível enquanto a base de dados não estiver configurada",
        )
    try:
        return await repository.list_open_data(dataset, limit=limit, offset=offset)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _metadata(dataset: str, limit: int, offset: int) -> dict[str, object]:
    return {
        "dataset": dataset,
        "schema_version": "2.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "limit": limit,
        "offset": offset,
        "publication_rule": (
            "Apenas registos publicados e verificados; identificadores pessoais protegidos, "
            "dados de contacto e candidatos de correspondência são excluídos."
        ),
        "provenance": "Cada linha conserva source_url e source_sha256 quando aplicável.",
    }


@router.get("/{dataset}.json")
async def export_json(
    dataset: OpenDataset,
    repository: Annotated[PostgresRepository, Depends(get_repository)],
    limit: int = Query(default=1_000, ge=1),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    maximum = get_settings().open_data_max_rows
    if limit > maximum:
        raise HTTPException(status_code=422, detail=f"limit não pode exceder {maximum}")
    rows = await _rows(dataset, repository, limit, offset)
    body = {**_metadata(dataset, limit, offset), "records": jsonable_encoder(rows)}
    return JSONResponse(body, headers={"Cache-Control": "public, max-age=300"})


@router.get("/{dataset}.csv")
async def export_csv(
    dataset: OpenDataset,
    repository: Annotated[PostgresRepository, Depends(get_repository)],
    limit: int = Query(default=1_000, ge=1),
    offset: int = Query(default=0, ge=0),
) -> StreamingResponse:
    maximum = get_settings().open_data_max_rows
    if limit > maximum:
        raise HTTPException(status_code=422, detail=f"limit não pode exceder {maximum}")
    rows = jsonable_encoder(await _rows(dataset, repository, limit, offset))
    output = io.StringIO(newline="")
    fieldnames = sorted({key for row in rows for key in row}) if rows else ["no_records"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: (
                    json.dumps(value, ensure_ascii=False, sort_keys=True)
                    if isinstance(value, (dict, list))
                    else value
                )
                for key, value in row.items()
            }
        )
    payload = output.getvalue().encode("utf-8")
    return StreamingResponse(
        iter([payload]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="transparencia-total-{dataset}.csv"',
            "Cache-Control": "public, max-age=300",
            "X-Open-Data-Schema": "2.0",
        },
    )
