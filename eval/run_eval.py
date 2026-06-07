"""
Ragas-powered evaluation pipeline for the DS Interview Coach RAG system.

Runs 5 metrics (faithfulness, answer_relevancy, context_precision, context_recall,
answer_correctness) on a golden test set, then compares against a stored baseline
to detect regressions.

Usage:
    # Full eval with regression check
    python eval/run_eval.py

    # Save current results as new baseline
    python eval/run_eval.py --save-baseline

    # Eval a subset for speed
    python eval/run_eval.py --subset 5

    # Filter by company or round
    python eval/run_eval.py --company BCG --round OA
"""

import argparse
import json
import logging
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path

# ── Env ──
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

warnings.filterwarnings("ignore", category=DeprecationWarning)

from ragas import SingleTurnSample, EvaluationDataset, evaluate
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.metrics._faithfulness import faithfulness
from ragas.metrics._answer_relevance import answer_relevancy
from ragas.metrics._context_precision import context_precision
from ragas.metrics._context_recall import context_recall
from ragas.metrics._answer_correctness import answer_correctness
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings

from rag.retriever import retrieve
from rag.generator import generate

log = logging.getLogger("eval")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

# ── Paths ──
GOLDEN_SET   = Path(__file__).parent / "golden_set.json"
BASELINE     = Path(__file__).parent / "baseline.json"
RESULTS_DIR  = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ── Regression gate ──
REGRESSION_THRESHOLD = 0.05


def _setup_ragas() -> None:
    """Wire Groq LLM + bge-large embeddings into the metric singletons."""
    llm = LangchainLLMWrapper(
        ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0,
            api_key=os.environ["GROQ_API_KEY"],
        )
    )
    emb = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(
            model_name="BAAI/bge-large-en-v1.5",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    )

    faithfulness.llm = llm
    context_precision.llm = llm
    context_recall.llm = llm

    answer_relevancy.llm = llm
    answer_relevancy.embeddings = emb

    answer_correctness.llm = llm
    answer_correctness.embeddings = emb


def _run_pipeline(question: dict) -> dict | None:
    """Retrieve + generate for one golden set question."""
    query      = question["question"]
    company    = question.get("company")
    round_type = question.get("round_type")

    company_filter = company    if company    not in (None, "Both") else None
    round_filter   = round_type if round_type not in (None, "All")  else None

    try:
        chunks = retrieve(
            query=query,
            top_k=6,
            company_filter=company_filter,
            round_filter=round_filter,
            use_hyde=True,
            use_multi_query=True,
        )
    except Exception as e:
        log.error(f"  retrieval failed for {question['id']}: {e}")
        return None

    try:
        answer = generate(query=query, chunks=chunks, stream=False)
    except Exception as e:
        log.error(f"  generation failed for {question['id']}: {e}")
        return None

    return {
        "id":        question["id"],
        "question":  query,
        "company":   question.get("company", "Both"),
        "round":     question.get("round_type", "General"),
        "reference": question.get("reference", ""),
        "contexts":  [c["text"] for c in chunks],
        "answer":    answer,
        "tags":      question.get("tags", []),
    }


def _build_samples(results: list[dict]) -> list[SingleTurnSample]:
    return [
        SingleTurnSample(
            user_input=r["question"],
            retrieved_contexts=r["contexts"],
            response=r["answer"],
            reference=r["reference"],
        )
        for r in results
    ]


def _regression_check(current: dict[str, float], baseline: dict[str, float]) -> list[str]:
    failures = []
    for metric, score in current.items():
        if metric not in baseline:
            continue
        drop = baseline[metric] - score
        if drop > REGRESSION_THRESHOLD:
            failures.append(
                f"{metric}: {score:.4f} (baseline {baseline[metric]:.4f}, drop {drop:.4f})"
            )
    return failures


def _print_table(scores: dict[str, float], baseline: dict[str, float] | None = None) -> None:
    print("\n" + "─" * 60)
    print(f"  {'Metric':<30}  {'Score':>7}  {'Baseline':>9}  {'Delta':>7}")
    print("─" * 60)
    for metric, score in scores.items():
        base_str = delta_str = ""
        if baseline and metric in baseline:
            b = baseline[metric]
            d = score - b
            base_str  = f"{b:.4f}"
            delta_str = f"{d:+.4f}"
        print(f"  {metric:<30}  {score:.4f}   {base_str:>8}  {delta_str:>8}")
    print("─" * 60 + "\n")


def run_eval(args: argparse.Namespace) -> int:
    """Main evaluation function. Returns exit code (0 = pass, 1 = regression)."""

    questions: list[dict] = json.loads(GOLDEN_SET.read_text())

    if args.company:
        questions = [q for q in questions if q.get("company") in (args.company, "Both")]
    if args.round:
        questions = [q for q in questions if q.get("round_type") == args.round]
    if args.subset:
        questions = questions[: args.subset]

    log.info(f"Running eval on {len(questions)} questions")

    # ── Step 1: Retrieve + generate ──
    pipeline_results: list[dict] = []
    for i, q in enumerate(questions, 1):
        log.info(f"  [{i}/{len(questions)}] {q['id']}")
        r = _run_pipeline(q)
        if r:
            pipeline_results.append(r)

    if not pipeline_results:
        log.error("No results produced — aborting.")
        return 1

    log.info(f"Pipeline produced {len(pipeline_results)}/{len(questions)} answers")

    # ── Step 2: Wire up Ragas metrics ──
    log.info("Loading evaluator LLM (Groq llama-3.3-70b) and embeddings (bge-large)…")
    _setup_ragas()

    # ── Step 3: Build dataset and evaluate ──
    dataset = EvaluationDataset(samples=_build_samples(pipeline_results))

    log.info("Running Ragas evaluation…")
    ragas_result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall, answer_correctness],
    )

    scores: dict[str, float] = {
        k: float(v) for k, v in ragas_result.items()
        if isinstance(v, (int, float))
    }

    # ── Step 4: Load baseline and print ──
    baseline: dict[str, float] | None = None
    if BASELINE.exists():
        baseline = json.loads(BASELINE.read_text()).get("scores")

    _print_table(scores, baseline)

    # ── Step 5: Save results ──
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = RESULTS_DIR / f"eval_{timestamp}.json"

    per_sample = []
    try:
        df = ragas_result.to_pandas()
        per_sample = df.to_dict(orient="records")
    except Exception:
        pass

    result_path.write_text(json.dumps({
        "timestamp":     timestamp,
        "n_questions":   len(pipeline_results),
        "filters":       {"company": args.company, "round": args.round},
        "scores":        scores,
        "baseline":      baseline,
        "per_sample":    per_sample,
        "pipeline_dump": pipeline_results,
    }, indent=2, default=str))
    log.info(f"Results saved → {result_path}")

    # ── Step 6: Optionally save as new baseline ──
    if args.save_baseline:
        BASELINE.write_text(json.dumps({"timestamp": timestamp, "scores": scores}, indent=2))
        log.info(f"Baseline updated → {BASELINE}")

    # ── Step 7: Regression gate ──
    exit_code = 0
    if baseline:
        failures = _regression_check(scores, baseline)
        if failures:
            log.error("REGRESSION DETECTED — the following metrics dropped >5%:")
            for f in failures:
                log.error(f"  ✗ {f}")
            exit_code = 1
        else:
            log.info("✓ Regression gate passed — no metric dropped >5% from baseline")
    else:
        log.info("No baseline found — run with --save-baseline to set one")

    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description="Ragas eval for DS Interview Coach RAG")
    parser.add_argument("--save-baseline", action="store_true",
                        help="Save current results as the new baseline")
    parser.add_argument("--subset", type=int, default=None,
                        help="Only evaluate the first N questions (for speed)")
    parser.add_argument("--company", choices=["BCG", "McKinsey", "Both"], default=None,
                        help="Filter golden set by company")
    parser.add_argument("--round", default=None,
                        help="Filter by round type (OA, Technical, LiveCoding, …)")
    args = parser.parse_args()

    sys.exit(run_eval(args))


if __name__ == "__main__":
    main()
