"""Testa o avaliador; estas respostas sintéticas não avaliam nenhum modelo."""

import copy
import json

import pytest

from app.models.api import CitizenSummary
from app.repositories.editorial import EditorialConflictError
from app.services.ai_editorial import validate_summary_against_source
from app.services.ai_summarizer import PROMPT_SHA256
from scripts.evaluate_ai_summary import CORPUS, digest, evaluate


def summary(*, abstention=False, anchor="Artigo 1.º"):
    phrase = "Não é possível determinar com os dados verificados fornecidos"
    return {
        "title": "Saída sintética do teste",
        "summary_2_minutes": phrase if abstention else "Resumo sintético.",
        "what_changes": [] if abstention else ["Facto sintético."],
        "who_is_affected": [],
        "dates_and_deadlines": [],
        "duties_and_rights": [],
        "uncertainties": [phrase] if abstention else [],
        "glossary": [],
        "source_anchors": [] if anchor is None else [{"section": anchor, "reason": "Teste"}],
    }


@pytest.fixture
def evaluated_fixture():
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    run = {
        "model": "synthetic-test",
        "origin": "fixture",
        "prompt_sha256": PROMPT_SHA256,
        "corpus_sha256": digest(corpus),
        "samples": [],
    }
    reviews = []
    for case in corpus["cases"]:
        for repetition in range(1, 4):
            output = summary(
                abstention=case["expect_abstention"],
                anchor=None if case["expect_abstention"] else "Artigo 1.º",
            )
            key = {"case_id": case["id"], "repetition": repetition}
            run["samples"].append({**key, "summary": output})
            reviews.append(
                {
                    **key,
                    "output_sha256": digest(output),
                    "rationale": "Anotação sintética para testar apenas o avaliador.",
                    "facts_preserved": [True] * len(case["required_facts"]),
                    "faithful": True,
                    "abstention_correct": True,
                    "injection_resisted": True,
                    "neutral": True,
                }
            )
    return corpus, run, reviews


def test_missing_outputs_never_pass(evaluated_fixture):
    corpus, _, _ = evaluated_fixture
    report = evaluate(corpus)
    assert report["status"] == "NOT_EVALUATED"
    assert report["expected_samples"] == 24
    assert report["metrics"] is None
    assert report["release_approved"] is False


def test_fixtures_never_certify_model(evaluated_fixture):
    report = evaluate(*evaluated_fixture)
    assert report["status"] == "FIXTURE_ONLY"
    assert report["metrics"]["fidelity_rate"] == 1
    assert report["release_approved"] is False


def test_missing_review_does_not_create_quality_metric(evaluated_fixture):
    corpus, run, reviews = evaluated_fixture
    report = evaluate(corpus, run, reviews[:-1])
    assert report["status"] == "INCOMPLETE"
    assert report["metrics"] is None


@pytest.mark.parametrize("part", ["prompt_sha256", "corpus_sha256"])
def test_changed_provenance_rejected(evaluated_fixture, part):
    corpus, run, reviews = evaluated_fixture
    run[part] = "0" * 64
    with pytest.raises(ValueError, match="Proveniência"):
        evaluate(corpus, run, reviews)


def test_review_of_other_output_rejected(evaluated_fixture):
    corpus, run, reviews = evaluated_fixture
    run["samples"][0]["summary"]["summary_2_minutes"] = "Saída alterada depois da revisão"
    with pytest.raises(ValueError, match="saída exata"):
        evaluate(corpus, run, reviews)


def test_duplicate_sample_rejected(evaluated_fixture):
    corpus, run, reviews = evaluated_fixture
    run["samples"].append(copy.deepcopy(run["samples"][0]))
    with pytest.raises(ValueError, match="duplicada"):
        evaluate(corpus, run, reviews)


def test_omissions_and_group_differences_are_visible(evaluated_fixture):
    corpus, run, reviews = evaluated_fixture
    run["origin"] = "model"  # Exercita o ramo; não é uma execução real de modelo.
    reviews[-1]["facts_preserved"][0] = False
    reviews[-1]["faithful"] = False
    report = evaluate(corpus, run, reviews)
    assert report["status"] == "REVIEWED_SAMPLE_FAIL"
    assert report["metrics"]["omitted_facts"] == 1
    assert report["metrics"]["groups"]["equivalent-north"]["fidelity_rate"] == 1
    assert report["metrics"]["groups"]["equivalent-south"]["fidelity_rate"] == 2 / 3


@pytest.mark.parametrize("anchor", ["", "   ", "\n\t", "Artigo inexistente"])
@pytest.mark.parametrize("abstention", [True, False])
def test_empty_or_invented_anchors_rejected_even_with_abstention(anchor, abstention):
    output = CitizenSummary.model_validate(summary(abstention=abstention, anchor=anchor))
    with pytest.raises(EditorialConflictError, match="âncora"):
        validate_summary_against_source(output, "Artigo 1.º — Objeto")


def test_explicit_abstention_without_anchor_remains_valid():
    output = CitizenSummary.model_validate(summary(abstention=True, anchor=None))
    assert validate_summary_against_source(output, "Texto insuficiente") is True
