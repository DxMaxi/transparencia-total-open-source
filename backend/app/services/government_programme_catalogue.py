"""Extração determinística de itens explicitamente enumerados no Programa oficial.

O resultado é um catálogo de candidatos privados. Encontrar um item numa lista
não prova que seja uma promessa autónoma, não define critérios de cumprimento e
nunca autoriza publicação.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from app.models.government_programme import (
    GovernmentProgrammeCatalogue,
    GovernmentProgrammeCatalogueBlock,
    GovernmentProgrammeCatalogueManifest,
    GovernmentProgrammeCoverage,
    GovernmentPromiseCandidate,
)

DEFAULT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "xxv-government-programme-catalogue-v2.json"
)

_HEADER = "Programa XXV Governo Constitucional"
_NUMBERED_MARKER = re.compile(r"^(?P<marker>\d+)\.\s+(?P<text>.+)$")
_LETTERED_MARKER = re.compile(r"^(?P<marker>[a-z])\.\s+(?P<text>.+)$")
_SPECIAL_MARKER = re.compile(r"^(?P<marker>[•▪-])\s+(?P<text>.+)$")
_UPPERCASE_START = re.compile(r"^[\"“«(]*[A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ]")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LIST_GLYPHS = frozenset({"l", "o", "", "•", "▪", "-"})


class GovernmentProgrammeCatalogueError(ValueError):
    """O PDF, o manifesto ou a extração deixaram de coincidir."""


@dataclass(frozen=True, slots=True)
class _PageLine:
    text: str
    x: float
    medium: bool


@dataclass(slots=True)
class _OpenCandidate:
    ordinal: int
    parent_ordinal: int | None
    hierarchy_level: int
    source_marker: str
    section_path: str
    programme_page_start: int
    programme_page_end: int
    marker_indent: float
    lines: list[str]


@dataclass(frozen=True, slots=True)
class _ExtractedCandidate:
    ordinal: int
    parent_ordinal: int | None
    hierarchy_level: int
    source_marker: str
    section_path: str
    programme_page_start: int
    programme_page_end: int
    statement_text: str


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


def _normalise_line(value: str) -> str:
    value = value.replace("\u00ad", "").replace("\ufeff", "")
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\s+([,.;:!?%)\]])", r"\1", value)
    value = re.sub(r"([(\[])\s+", r"\1", value)
    value = re.sub(r"(?<=\d)\s+\.\s*(?=º|ª)", ".", value)
    # O PDF separa pontualmente a primeira letra de três palavras no seu
    # content stream. A lista é fechada para não transformar artigos legítimos.
    value = value.replace("I novação", "Inovação")
    value = value.replace("A valiação", "Avaliação")
    value = value.replace("A vançar", "Avançar")
    return value


def _normalise_anchor(value: str) -> str:
    value = _normalise_line(value)
    value = re.sub(r"(?<=\d)\s+\.", ".", value)
    value = re.sub(r"(?<=\d)\.\s+(?=\d+\.)", ".", value)
    value = re.sub(r"(?<=\d)\.\s+(?=[A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ])", ". ", value)
    return value


def _anchor_matches(line: str, anchor: str) -> bool:
    observed = _normalise_anchor(line)
    expected = _normalise_anchor(anchor)
    return observed == expected or observed.startswith(f"{expected} ")


def _page_lines(reader: PdfReader, page_number: int) -> list[_PageLine]:
    fragments_by_y: dict[float, list[tuple[float, str, bool]]] = {}
    last_positioned: tuple[float, float, str, bool] | None = None

    def visitor(
        text: str,
        _cm: list[float],
        text_matrix: list[float],
        font_dictionary: dict[str, Any] | None,
        _font_size: float,
    ) -> None:
        nonlocal last_positioned
        base_font = str((font_dictionary or {}).get("/BaseFont", ""))
        candidate = " ".join(text.replace("\u00ad", "").split())
        if not candidate:
            return
        x = float(text_matrix[4])
        y = float(text_matrix[5])
        medium = "PortuguesaSerif-Medium" in base_font

        if x == 0.0 and y == 0.0:
            if candidate == "-" and last_positioned is not None:
                previous_x, previous_y, _previous_text, previous_medium = last_positioned
                fragments_by_y.setdefault(previous_y, []).append(
                    (previous_x + 500.0, candidate, previous_medium)
                )
                return
            if last_positioned is None or last_positioned[2] not in _LIST_GLYPHS:
                return
            previous_x, previous_y, _previous_text, previous_medium = last_positioned
            x = previous_x + 20.0
            y = previous_y
            medium = previous_medium

        if x < 50.0 or x > 600.0 or y < 50.0 or y > 760.0:
            return
        y_key = round(y, 1)
        fragments_by_y.setdefault(y_key, []).append((x, candidate, medium))
        last_positioned = (x, y_key, candidate, medium)

    reader.pages[page_number - 1].extract_text(visitor_text=visitor)
    lines: list[_PageLine] = []
    for _y, fragments in sorted(fragments_by_y.items(), reverse=True):
        fragments.sort(key=lambda item: item[0])
        text_value = ""
        for _x, fragment, _medium in fragments:
            if fragment == "-" and text_value:
                text_value = f"{text_value}-"
            elif not text_value:
                text_value = fragment
            else:
                text_value = f"{text_value} {fragment}"
        line = _normalise_line(text_value)
        if not line or line.startswith(_HEADER) or re.fullmatch(r"\d+(?:\s+\d+)?", line):
            continue
        lines.append(
            _PageLine(
                text=line,
                x=min(fragment[0] for fragment in fragments),
                medium=any(fragment[2] for fragment in fragments),
            )
        )
    return lines


def _is_heading(line: _PageLine) -> bool:
    if line.text.startswith(("Medidas principais", "Medidas para ")):
        return True
    letters = [character for character in line.text if character.isalpha()]
    all_uppercase = len(letters) >= 4 and all(character.isupper() for character in letters)
    return line.medium or all_uppercase


def _marker(line: str) -> tuple[str, int, str] | None:
    match = _NUMBERED_MARKER.match(line)
    if match:
        return f"{match.group('marker')}.", 1, match.group("text")
    match = _LETTERED_MARKER.match(line)
    if match:
        return f"{match.group('marker')}.", 2, match.group("text")
    match = _SPECIAL_MARKER.match(line)
    if match:
        return match.group("marker"), 3, match.group("text")
    for bullet, level in (("l", 1), ("o", 2)):
        prefix = f"{bullet} "
        if line.startswith(prefix):
            text = line[len(prefix) :]
            if _UPPERCASE_START.match(text):
                return bullet, level, text
    return None


def _join_statement(lines: Iterable[str]) -> str:
    statement = ""
    for line in lines:
        if not statement:
            statement = line
        elif statement.endswith("-"):
            statement = f"{statement[:-1]}{line}"
        else:
            statement = f"{statement} {line}"
    statement = _normalise_line(statement)
    if len(statement) < 3:
        raise GovernmentProgrammeCatalogueError("Foi extraído um item sem texto suficiente")
    if len(statement) > 12_000:
        raise GovernmentProgrammeCatalogueError("Um item excede o limite editorial de 12 000")
    return statement


def _candidate_digest_payload(candidate: GovernmentPromiseCandidate) -> dict[str, object]:
    return {
        "candidate_key": candidate.candidate_key,
        "block_id": candidate.block_id,
        "ordinal": candidate.ordinal,
        "parent_ordinal": candidate.parent_ordinal,
        "hierarchy_level": candidate.hierarchy_level,
        "source_marker": candidate.source_marker,
        "area": candidate.area,
        "section_path": candidate.section_path,
        "programme_page_start": candidate.programme_page_start,
        "programme_page_end": candidate.programme_page_end,
        "statement_sha256": candidate.statement_sha256,
        "source_locator_sha256": candidate.source_locator_sha256,
    }


def verify_government_programme_catalogue(
    *,
    catalogue: GovernmentProgrammeCatalogue,
    manifest: GovernmentProgrammeCatalogueManifest,
) -> None:
    """Reconstrói todas as provas normalizadas antes de permitir persistência."""

    expected_layout_sha256 = _sha256_json(manifest.model_dump(mode="json"))
    if (
        catalogue.source_sha256 != manifest.source_sha256
        or catalogue.source_byte_size != manifest.source_byte_size
        or catalogue.source_page_count != manifest.source_page_count
        or catalogue.layout_manifest_sha256 != expected_layout_sha256
    ):
        raise GovernmentProgrammeCatalogueError(
            "A identidade do catálogo diverge do PDF ou do manifesto revisto"
        )
    if len(catalogue.candidates) != manifest.expected_candidate_count:
        raise GovernmentProgrammeCatalogueError(
            "A contagem total de candidatos diverge do catálogo revisto"
        )
    expected_catalogue_sha256 = _sha256_json(
        [_candidate_digest_payload(candidate) for candidate in catalogue.candidates]
    )
    if (
        catalogue.catalogue_sha256 != expected_catalogue_sha256
        or catalogue.catalogue_sha256 != manifest.expected_catalogue_sha256
    ):
        raise GovernmentProgrammeCatalogueError(
            "O SHA-256 normalizado do catálogo diverge do catálogo revisto"
        )

    blocks = {block.block_id: block for block in manifest.blocks}
    coverage_by_block = {item.block_id: item for item in catalogue.coverage}
    if len(coverage_by_block) != len(catalogue.coverage) or set(coverage_by_block) != set(blocks):
        raise GovernmentProgrammeCatalogueError(
            "O livro de cobertura não coincide exatamente com os blocos do manifesto"
        )
    candidates_by_block: dict[str, list[GovernmentPromiseCandidate]] = {
        block_id: [] for block_id in blocks
    }
    for candidate in catalogue.candidates:
        block = blocks.get(candidate.block_id)
        if block is None:
            raise GovernmentProgrammeCatalogueError(
                f"O candidato {candidate.candidate_key} pertence a um bloco desconhecido"
            )
        if candidate.area != block.area or not (
            candidate.section_path == block.section_path
            or candidate.section_path.startswith(f"{block.section_path} > ")
        ):
            raise GovernmentProgrammeCatalogueError(
                f"O candidato {candidate.candidate_key} diverge da secção oficial"
            )
        if not (
            block.start_page
            <= candidate.programme_page_start
            <= candidate.programme_page_end
            <= block.end_page
        ):
            raise GovernmentProgrammeCatalogueError(
                f"O candidato {candidate.candidate_key} diverge das páginas do bloco"
            )
        statement_sha256 = hashlib.sha256(candidate.statement_text.encode()).hexdigest()
        locator_sha256 = _sha256_json(
            {
                "source_sha256": catalogue.source_sha256,
                "block_id": candidate.block_id,
                "ordinal": candidate.ordinal,
                "source_marker": candidate.source_marker,
                "section_path": candidate.section_path,
                "programme_page_start": candidate.programme_page_start,
                "programme_page_end": candidate.programme_page_end,
            }
        )
        key_sha256 = hashlib.sha256(
            (
                f"{catalogue.source_sha256}:{candidate.block_id}:{candidate.ordinal}:"
                f"{locator_sha256}:{statement_sha256}"
            ).encode()
        ).hexdigest()
        if (
            candidate.statement_sha256 != statement_sha256
            or candidate.source_locator_sha256 != locator_sha256
            or candidate.candidate_key != f"xxv-candidate-{key_sha256}"
        ):
            raise GovernmentProgrammeCatalogueError(
                f"Os hashes do candidato {candidate.candidate_key} não são reconstruíveis"
            )
        candidates_by_block[candidate.block_id].append(candidate)

    for block_id, block in blocks.items():
        block_candidates = candidates_by_block[block_id]
        ordinals = [candidate.ordinal for candidate in block_candidates]
        if ordinals != list(range(1, len(block_candidates) + 1)):
            raise GovernmentProgrammeCatalogueError(
                f"A sequência de itens do bloco {block_id} não é contínua"
            )
        if any(
            candidate.parent_ordinal is not None and candidate.parent_ordinal >= candidate.ordinal
            for candidate in block_candidates
        ):
            raise GovernmentProgrammeCatalogueError(
                f"A hierarquia do bloco {block_id} referencia um item inválido"
            )
        block_sha256 = _sha256_json(
            [_candidate_digest_payload(candidate) for candidate in block_candidates]
        )
        observed = coverage_by_block[block_id]
        if (
            observed.part != block.part
            or observed.area != block.area
            or observed.section_path != block.section_path
            or observed.start_page != block.start_page
            or observed.end_page != block.end_page
            or observed.start_anchor != block.start_anchor
            or observed.end_anchor != block.end_anchor
            or observed.candidate_count != len(block_candidates)
            or observed.candidate_count != block.expected_candidate_count
            or observed.block_sha256 != block_sha256
            or observed.block_sha256 != block.expected_block_sha256
        ):
            raise GovernmentProgrammeCatalogueError(
                f"O bloco {block_id} diverge da revisão explícita do manifesto"
            )


def _extract_block(
    *,
    reader: PdfReader,
    source_sha256: str,
    block: GovernmentProgrammeCatalogueBlock,
) -> tuple[tuple[GovernmentPromiseCandidate, ...], GovernmentProgrammeCoverage]:
    selected: list[tuple[int, _PageLine]] = []
    start_found = False
    end_found = block.end_anchor is None

    for page_number in range(block.start_page, block.end_page + 1):
        for line in _page_lines(reader, page_number):
            if not start_found:
                if _anchor_matches(line.text, block.start_anchor):
                    start_found = True
                continue
            if block.end_anchor is not None and _anchor_matches(line.text, block.end_anchor):
                end_found = True
                break
            selected.append((page_number, line))
        if end_found and block.end_anchor is not None:
            break

    if not start_found:
        raise GovernmentProgrammeCatalogueError(
            f"Âncora inicial não encontrada no bloco {block.block_id}: {block.start_anchor}"
        )
    if not end_found:
        raise GovernmentProgrammeCatalogueError(
            f"Âncora final não encontrada no bloco {block.block_id}: {block.end_anchor}"
        )

    raw_candidates: list[_ExtractedCandidate] = []
    current: _OpenCandidate | None = None
    current_section = block.section_path
    level_stack: dict[int, int] = {}

    def finish_current() -> None:
        nonlocal current
        if current is None:
            return
        raw_candidates.append(
            _ExtractedCandidate(
                ordinal=current.ordinal,
                parent_ordinal=current.parent_ordinal,
                hierarchy_level=current.hierarchy_level,
                source_marker=current.source_marker,
                section_path=current.section_path,
                programme_page_start=current.programme_page_start,
                programme_page_end=current.programme_page_end,
                statement_text=_join_statement(current.lines),
            )
        )
        current = None

    for page_number, line in selected:
        marker = _marker(line.text)
        if marker is not None:
            finish_current()
            source_marker, hierarchy_level, first_line = marker
            ordinal = len(raw_candidates) + 1
            parent_ordinal = max(
                (value for level, value in level_stack.items() if level < hierarchy_level),
                default=None,
            )
            for level in tuple(level_stack):
                if level >= hierarchy_level:
                    del level_stack[level]
            level_stack[hierarchy_level] = ordinal
            current = _OpenCandidate(
                ordinal=ordinal,
                parent_ordinal=parent_ordinal,
                hierarchy_level=hierarchy_level,
                source_marker=source_marker,
                section_path=current_section,
                programme_page_start=page_number,
                programme_page_end=page_number,
                marker_indent=line.x,
                lines=[first_line],
            )
            continue
        if _is_heading(line):
            finish_current()
            current_section = f"{block.section_path} > {line.text}"[:300]
            level_stack.clear()
            continue
        if current is not None:
            if line.x + 8.0 < current.marker_indent:
                finish_current()
                level_stack.clear()
                continue
            current.lines.append(line.text)
            current.programme_page_end = page_number

    finish_current()
    if not raw_candidates:
        raise GovernmentProgrammeCatalogueError(
            f"O bloco {block.block_id} não produziu itens explicitamente enumerados"
        )

    candidates: list[GovernmentPromiseCandidate] = []
    for item in raw_candidates:
        statement_text = item.statement_text
        statement_sha256 = hashlib.sha256(statement_text.encode("utf-8")).hexdigest()
        locator = {
            "source_sha256": source_sha256,
            "block_id": block.block_id,
            "ordinal": item.ordinal,
            "source_marker": item.source_marker,
            "section_path": item.section_path,
            "programme_page_start": item.programme_page_start,
            "programme_page_end": item.programme_page_end,
        }
        source_locator_sha256 = _sha256_json(locator)
        key_digest = hashlib.sha256(
            (
                f"{source_sha256}:{block.block_id}:{item.ordinal}:"
                f"{source_locator_sha256}:{statement_sha256}"
            ).encode()
        ).hexdigest()
        candidates.append(
            GovernmentPromiseCandidate(
                candidate_key=f"xxv-candidate-{key_digest}",
                block_id=block.block_id,
                ordinal=item.ordinal,
                parent_ordinal=item.parent_ordinal,
                hierarchy_level=item.hierarchy_level,
                source_marker=item.source_marker,
                area=block.area,
                section_path=item.section_path,
                programme_page_start=item.programme_page_start,
                programme_page_end=item.programme_page_end,
                statement_text=statement_text,
                statement_sha256=statement_sha256,
                source_locator_sha256=source_locator_sha256,
            )
        )

    block_sha256 = _sha256_json([_candidate_digest_payload(item) for item in candidates])
    coverage = GovernmentProgrammeCoverage(
        block_id=block.block_id,
        part=block.part,
        area=block.area,
        section_path=block.section_path,
        start_page=block.start_page,
        end_page=block.end_page,
        start_anchor=block.start_anchor,
        end_anchor=block.end_anchor,
        candidate_count=len(candidates),
        block_sha256=block_sha256,
    )
    return tuple(candidates), coverage


def load_government_programme_manifest(
    path: Path = DEFAULT_MANIFEST_PATH,
) -> GovernmentProgrammeCatalogueManifest:
    value = json.loads(path.read_text(encoding="utf-8"))
    return GovernmentProgrammeCatalogueManifest.model_validate(value)


def extract_government_programme_catalogue(
    *,
    pdf_bytes: bytes,
    manifest: GovernmentProgrammeCatalogueManifest,
    verify_manifest: bool = True,
) -> GovernmentProgrammeCatalogue:
    source_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    if source_sha256 != manifest.source_sha256 or len(pdf_bytes) != manifest.source_byte_size:
        raise GovernmentProgrammeCatalogueError(
            "Os bytes do Programa do Governo não coincidem com a versão revista no manifesto"
        )

    reader = PdfReader(io.BytesIO(pdf_bytes))
    if len(reader.pages) != manifest.source_page_count:
        raise GovernmentProgrammeCatalogueError(
            "A contagem de páginas do Programa do Governo diverge do manifesto"
        )

    all_candidates: list[GovernmentPromiseCandidate] = []
    coverage: list[GovernmentProgrammeCoverage] = []
    for block in manifest.blocks:
        block_candidates, block_coverage = _extract_block(
            reader=reader,
            source_sha256=source_sha256,
            block=block,
        )
        all_candidates.extend(block_candidates)
        coverage.append(block_coverage)

    catalogue_sha256 = _sha256_json(
        [_candidate_digest_payload(candidate) for candidate in all_candidates]
    )
    layout_manifest_sha256 = _sha256_json(manifest.model_dump(mode="json"))
    result = GovernmentProgrammeCatalogue(
        source_sha256=source_sha256,
        source_byte_size=len(pdf_bytes),
        source_page_count=len(reader.pages),
        layout_manifest_sha256=layout_manifest_sha256,
        catalogue_sha256=catalogue_sha256,
        candidates=tuple(all_candidates),
        coverage=tuple(coverage),
    )

    if verify_manifest:
        verify_government_programme_catalogue(catalogue=result, manifest=manifest)

    if not _SHA256.fullmatch(result.catalogue_sha256):
        raise GovernmentProgrammeCatalogueError("O digest final do catálogo é inválido")
    return result
