"""Hello-world LLM call used by the Phase 1 instrumentation pass.

Proves the wires: AI Gateway round-trip + trace_log write + Lapdog capture
(when wrapped) + Datadog cloud forward (when DD_API_KEY is set).
"""

from __future__ import annotations

from paperpilot import trace
from paperpilot.gateway import DEFAULTS, get_client


PROMPT = (
    "In one sentence, name three sponsors at this NYC agentic hackathon: "
    "Datadog, ClickHouse, Nimble, Luminai, DeepMind. Be punchy."
)


def ping(session_id: str) -> str:
    """Round-trip a small prompt through AI Gateway, fully traced."""
    client = get_client()
    model = DEFAULTS["draft"]

    with trace.step(session_id, "llm.ping", model=model, prompt_len=len(PROMPT)) as ctx:
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": PROMPT}],
            max_tokens=200,
        )
        text = completion.choices[0].message.content or ""
        usage = completion.usage
        ctx["tokens_in"] = getattr(usage, "prompt_tokens", None)
        ctx["tokens_out"] = getattr(usage, "completion_tokens", None)
        ctx["cost_usd"] = getattr(usage, "cost", None)
        ctx["finish_reason"] = completion.choices[0].finish_reason
        ctx["response_preview"] = text[:200]

    return text
