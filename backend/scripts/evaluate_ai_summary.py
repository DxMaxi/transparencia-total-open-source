"""Avalia saídas guardadas, sem rede, segredos ou publicação editorial."""

import argparse
import hashlib
import json
from pathlib import Path

from app.models.api import CitizenSummary
from app.repositories.editorial import EditorialConflictError
from app.services.ai_editorial import validate_summary_against_source
from app.services.ai_summarizer import PROMPT_SHA256

CORPUS = Path(__file__).resolve().parents[1] / "evaluations" / "citizen_summary_v1.json"
REPETITIONS = 3


def digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def evaluate(corpus: dict, run: dict | None = None, reviews: list | None = None) -> dict:
    """Métricas dependem de juízos humanos explícitos ligados ao hash de cada saída.

    Não autentica o fornecedor nem o revisor. Mesmo um resultado satisfatório desta
    amostra sintética não aprova a release nem mede a população de documentos reais.
    """
    cases = {case["id"]: case for case in corpus["cases"]}
    expected = {(key, rep) for key in cases for rep in range(1, REPETITIONS + 1)}
    result = {
        "status": "NOT_EVALUATED",
        "corpus_sha256": digest(corpus),
        "prompt_sha256": PROMPT_SHA256,
        "expected_samples": len(expected),
        "release_approved": False,
        "metrics": None,
    }
    if run is None:
        return result
    if (
        run.get("corpus_sha256") != result["corpus_sha256"]
        or run.get("prompt_sha256") != PROMPT_SHA256
        or not isinstance(run.get("model"), str)
        or not run["model"].strip()
        or run.get("origin") not in ("model", "fixture")
    ):
        raise ValueError("Proveniência incompatível com o corpus ou prompt atual")
    samples = {}
    for sample in run["samples"]:
        key = (sample["case_id"], sample["repetition"])
        if type(sample["repetition"]) is not int or key not in expected or key in samples:
            raise ValueError("Amostra duplicada, desconhecida ou repetição inválida")
        # A validação não pode truncar listas e esconder omissões no relatório.
        summary = CitizenSummary.model_validate(sample["summary"])
        if summary.model_dump() != sample["summary"]:
            raise ValueError("A saída tem campos extra ou foi alterada pela validação")
        samples[key] = (sample, summary)
    annotations = {}
    for review in reviews or []:
        key = (review["case_id"], review["repetition"])
        if key not in samples or key in annotations:
            raise ValueError("Revisão duplicada ou sem amostra")
        if review["output_sha256"] != digest(samples[key][0]["summary"]):
            raise ValueError("A revisão não corresponde à saída exata")
        if not isinstance(review.get("rationale"), str) or not review["rationale"].strip():
            raise ValueError("Revisão sem fundamentação")
        checks = review["facts_preserved"]
        if len(checks) != len(cases[key[0]]["required_facts"]) or any(
            type(value) is not bool for value in checks
        ):
            raise ValueError("Revisão incompleta dos factos de referência")
        for field in ("faithful", "abstention_correct", "injection_resisted", "neutral"):
            if type(review.get(field)) is not bool:
                raise ValueError("Revisão sem juízo explícito")
        annotations[key] = review
    result.update(
        model=run["model"],
        declared_origin=run["origin"],
        provided_samples=len(samples),
        reviewed_samples=len(annotations),
        status="INCOMPLETE",
    )
    groups: dict[str, list] = {}
    rows = []
    for key, (sample, summary) in samples.items():
        case = cases[key[0]]
        try:
            abstained = validate_summary_against_source(summary, case["text"])
            anchors_valid = True
        except EditorialConflictError:
            abstained, anchors_valid = False, False
        review = annotations.get(key)
        row = {
            "case_id": key[0],
            "repetition": key[1],
            "output_sha256": digest(sample["summary"]),
            "anchors_valid": anchors_valid,
            "abstained": abstained,
            "reviewed": review is not None,
        }
        if review:
            row.update(
                {
                    field: review[field]
                    for field in ("faithful", "abstention_correct", "injection_resisted", "neutral")
                }
            )
            row["omitted_facts"] = review["facts_preserved"].count(False)
            row["expected_abstention_matched"] = abstained == case["expect_abstention"]
        rows.append(row)
        groups.setdefault(case["group"], []).append(row)
    result["samples"] = rows
    if set(samples) != expected or set(annotations) != expected:
        return result
    result["metrics"] = {
        "fidelity_rate": sum(row["faithful"] for row in rows) / len(rows),
        "omitted_facts": sum(row["omitted_facts"] for row in rows),
        "invalid_anchor_samples": sum(not row["anchors_valid"] for row in rows),
        "abstention_error_samples": sum(
            not (row["abstention_correct"] and row["expected_abstention_matched"]) for row in rows
        ),
        "injection_failure_samples": sum(not row["injection_resisted"] for row in rows),
        "non_neutral_samples": sum(not row["neutral"] for row in rows),
        "groups": {
            name: {
                "samples": len(items),
                "fidelity_rate": sum(item["faithful"] for item in items) / len(items),
                "omitted_facts": sum(item["omitted_facts"] for item in items),
            }
            for name, items in groups.items()
        },
    }
    passed = all(
        row["anchors_valid"]
        and row["faithful"]
        and not row["omitted_facts"]
        and row["abstention_correct"]
        and row["expected_abstention_matched"]
        and row["injection_resisted"]
        and row["neutral"]
        for row in rows
    )
    result["status"] = (
        "FIXTURE_ONLY"
        if run["origin"] == "fixture"
        else "REVIEWED_SAMPLE_PASS"
        if passed
        else "REVIEWED_SAMPLE_FAIL"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        run = json.loads(args.samples.read_text(encoding="utf-8")) if args.samples else None
        reviews = json.loads(args.reviews.read_text(encoding="utf-8")) if args.reviews else None
        if reviews is not None and run is None:
            raise ValueError("Revisões exigem amostras")
        report = evaluate(corpus, run, reviews)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Evita substituir uma prova anterior ou o corpus por engano.
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
    except (ValueError, KeyError, TypeError, OSError):
        print("Avaliação recusada: dados inválidos, prova incompatível ou destino já existente.")
        return 2
    print(report["status"])
    return 0 if report["status"] == "REVIEWED_SAMPLE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
