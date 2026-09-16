"""LLM-as-a-judge for `judge` cases: weighted dimensions against a hand-written reference,
multiplicative penalty when a number in the answer has no evidence in the tool outputs."""

from pydantic import BaseModel, Field

from src.llm import make_chat, model_for
from src.pricing import cost_usd

WEIGHTS = {"correctness": 0.5, "grounding": 0.3, "completeness": 0.2}
PENALTY = 0.3
PASS_AT = 0.7

PROMPT = """You grade an answer produced by a data agent over a small accounting ledger.
Compare it with the REFERENCE written by a human from the same data. Be strict on numbers.

Score each dimension from 0.0 to 1.0:
- correctness: are the facts and figures right and consistent with the reference?
- grounding: does every figure in the answer appear in, or follow arithmetically from,
  the TOOL OUTPUTS?
- completeness: does the answer cover what the question asks, as the reference does?
Set unsupported_number=true if ANY number in the answer has no evidence in the tool outputs.
If the agent refused or gave no answer, score 0 on all dimensions.

QUESTION:
{question}

REFERENCE:
{reference}

TOOL OUTPUTS (what the agent actually retrieved):
{tools}

ANSWER:
{answer}
"""


class Verdict(BaseModel):
    correctness: float
    grounding: float
    completeness: float
    unsupported_number: bool
    rationale: str = Field(description="two sentences max")

    def score(self) -> float:
        # clamp here: the Anthropic endpoint rejects minimum/maximum in tool schemas
        s = sum(min(1.0, max(0.0, getattr(self, k))) * w for k, w in WEIGHTS.items())
        return round(s * (PENALTY if self.unsupported_number else 1.0), 3)


def _fmt_tools(tool_calls: list) -> str:
    if not tool_calls:
        return "(no tools called)"
    return "\n".join(f"{c.name}({c.args}) -> {c.output[:1500]}" for c in tool_calls)


async def judge(case: dict, answer: str, tool_calls: list, seed: int | None = None) -> dict:
    llm = make_chat("judge", seed=seed).with_structured_output(
        Verdict, method="function_calling", include_raw=True
    )
    prompt = PROMPT.format(
        question=case["input"], reference=case["reference"], tools=_fmt_tools(tool_calls),
        answer=answer or "(empty)",
    )  # fmt: skip
    res = await llm.ainvoke(prompt)
    v: Verdict = res["parsed"]
    u = res["raw"].usage_metadata or {}
    cost, _ = cost_usd(model_for("judge"), u.get("input_tokens", 0), u.get("output_tokens", 0))
    return {"score": v.score(), "passed": v.score() >= PASS_AT, "verdict": v.model_dump(),
            "judge_cost_usd": cost}  # fmt: skip
