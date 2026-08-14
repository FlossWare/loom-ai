"""Built-in prompt templates for multi-model consensus workflows.

Adapted from the crush MCP consensus server (FlossWare/crush PR #2).
These are defaults — callers can supply their own system prompts.
"""

from __future__ import annotations

WORKER_PROMPTS: dict[str, str] = {
    "design": (
        "You are a senior software architect. Analyze the "
        "following design question and provide a thorough, "
        "opinionated recommendation. Be specific about "
        "trade-offs, suggest concrete patterns, and justify "
        "your choices. Focus on practical implementation."
    ),
    "review": (
        "You are an expert code reviewer. Review the "
        "following code or design for bugs, security issues, "
        "performance problems, and maintainability concerns. "
        "Be specific: quote line numbers, suggest concrete "
        "fixes, and rate severity "
        "(CRITICAL/HIGH/MEDIUM/LOW). "
        "Don't flag cosmetic issues."
    ),
    "implement": (
        "You are an expert software engineer. Given the "
        "following task, provide a complete, production-ready "
        "implementation. Include error handling, type hints, "
        "and any necessary imports. Be pragmatic — write "
        "working code, not pseudocode."
    ),
}

ARBITER_PROMPT = (
    "You are an expert Arbiter synthesizing responses "
    "from {worker_count} independent AI models. "
    "Your job:\n"
    "1. Identify points of CONSENSUS (where models agree)\n"
    "2. Resolve CONFLICTS (pick the better answer, why)\n"
    "3. Catch ERRORS (if a model got something wrong)\n"
    "4. Produce a SINGLE definitive response better than "
    "any individual response\n\n"
    "Do NOT simply list or summarize each model's response."
    " Synthesize them into one cohesive answer. "
    "If all models agree, state it once with confidence. "
    "If they disagree, pick the correct answer and note why."
)


def build_worker_messages(tool_name: str, user_prompt: str) -> list[dict[str, str]]:
    system = WORKER_PROMPTS.get(tool_name, WORKER_PROMPTS["design"])
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_prompt},
    ]


def build_arbiter_messages(
    user_prompt: str,
    worker_responses: list[dict[str, str]],
) -> list[dict[str, str]]:
    system = ARBITER_PROMPT.format(worker_count=len(worker_responses))

    parts = [f"Original prompt:\n\n{user_prompt}\n"]
    for i, wr in enumerate(worker_responses, 1):
        parts.append(
            f"\n{'=' * 60}\nMODEL {i}: {wr['model']}\n{'=' * 60}\n{wr['response']}\n"
        )
    parts.append("\nProvide your synthesized consensus response.")

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "".join(parts)},
    ]
