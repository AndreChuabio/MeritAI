"""Seed Senso KB with tone-reference exemplars for the drafter.

Run once before live demo. Idempotent in the sense that re-running just
adds more nodes (Senso de-dupes by content hash internally; we don't worry
about it for hackathon scope).

Usage:
    uv run python scripts/seed_senso.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from paperpilot import senso_client  # noqa: E402
from paperpilot.trace import new_session  # noqa: E402


load_dotenv()


# Tone-reference exemplars: 1 abstract + 1 related-work fragment for each
# of the venues we're most likely to draft for. Hand-curated to encode the
# academic register without leaking copyrighted prose.
EXEMPLARS: list[tuple[str, str]] = [
    (
        "ML4H abstract exemplar",
        (
            "Clinical decision support systems leveraging large language models "
            "promise to reduce documentation burden, yet their deployment in "
            "high-stakes settings is constrained by limited interpretability and "
            "patient-safety considerations. We propose a hybrid retrieval-augmented "
            "framework that grounds generated clinical summaries in verifiable "
            "structured data drawn from electronic health records. On a held-out "
            "cohort of 4,217 hospital admissions, our approach reduces factual "
            "inconsistency rates by 38% relative to baseline summarization "
            "pipelines while preserving informativeness as judged by board-certified "
            "clinicians. We discuss deployment implications, including audit-log "
            "requirements and the role of clinician-in-the-loop verification."
        ),
    ),
    (
        "ML4H related-work tone exemplar",
        (
            "Recent work in clinical natural language processing has explored "
            "retrieval-augmented generation as a path to factual reliability. "
            "Notably, prior efforts have grounded model outputs in domain-specific "
            "corpora such as discharge summaries and clinical guidelines, "
            "demonstrating reductions in unsupported claims. Complementary work on "
            "evaluation frameworks has highlighted the importance of clinician-judged "
            "metrics over surface-level lexical overlap. Our contribution extends "
            "these threads by introducing structured-data grounding alongside "
            "retrieval, addressing a gap identified in recent surveys."
        ),
    ),
    (
        "NeurIPS abstract exemplar",
        (
            "We introduce a method for efficient distributed training of medium-scale "
            "transformer language models that reduces communication overhead by "
            "exploiting structured sparsity in gradient updates. Across two language "
            "modeling benchmarks and three model scales (125M to 1.3B parameters), "
            "the approach attains 92-97% of the throughput of standard data-parallel "
            "training while requiring 4x less inter-node bandwidth. We provide an "
            "open-source implementation and ablate the contribution of each design "
            "choice. Our results suggest that bandwidth-aware optimizer state "
            "compression is a practical lever for academic training budgets."
        ),
    ),
    (
        "EMNLP abstract exemplar",
        (
            "Despite extensive study of in-context learning, the mechanisms by which "
            "large language models exploit demonstration ordering remain "
            "incompletely understood. We present a controlled empirical study "
            "across five model families and twelve text classification tasks, "
            "finding that performance differences attributable to permutation alone "
            "exceed the effects of demonstration choice in 60% of settings. We "
            "introduce a permutation-robust prompting strategy that closes the gap, "
            "validated on held-out tasks. We release task templates and analysis "
            "code to facilitate replication."
        ),
    ),
    (
        "Academic method-section tone exemplar",
        (
            "Our approach proceeds in three stages. First, we construct a retrieval "
            "index over the target corpus using a frozen sentence encoder. Second, "
            "at inference time, we condition the generator on the top-k retrieved "
            "passages, applying a learned re-ranker to filter spurious matches. "
            "Third, we apply a post-hoc verification step that compares generated "
            "claims against the retrieved context using a natural-language "
            "inference model. Each stage is independently ablated in the experiments "
            "section."
        ),
    ),
]


def main() -> None:
    if not senso_client.is_configured():
        print("SENSO_API_KEY not set. Skipping.")
        sys.exit(1)
    sid = new_session()
    print(f"Session: {sid}")
    print(f"Ingesting {len(EXEMPLARS)} exemplars into Senso KB...")
    ok = 0
    for title, text in EXEMPLARS:
        result = senso_client.ingest_raw(title=title, text=text, session_id=sid)
        if result is None:
            print(f"  FAIL  {title}")
        else:
            node_id = result.get("id") or result.get("node_id") or "?"
            print(f"  OK    {title}  (node={node_id})")
            ok += 1
    print()
    print(f"Done. {ok}/{len(EXEMPLARS)} ingested.")


if __name__ == "__main__":
    main()
