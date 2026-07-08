import json
from typing import Any

from modules.state import AnalystState
from modules.llm_client import get_openai_client
from modules.settings import get_openai_model


REPORT_LIKE_TERMS = [
    "full report",
    "create a full report",
    "generate report",
    "pdf report",
    "complete report",
    "download report",
    "export report",
]


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _is_report_request(question: str) -> bool:
    q = _normalize(question)
    return any(term in q for term in REPORT_LIKE_TERMS)


def _safe_json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def _limit_dict_items(data: dict, limit: int = 8) -> dict:
    if not isinstance(data, dict):
        return {}

    limited = {}

    for index, (key, value) in enumerate(data.items()):
        if index >= limit:
            break

        limited[key] = value

    return limited


def _build_compact_dataset_context(dataset_summary: dict) -> dict:
    """
    Compact dataset profile for LLM.
    Prevents Groq token overflow.
    """

    if not dataset_summary:
        return {
            "error": "No dataset summary available."
        }

    numeric_stats = dataset_summary.get("numeric_stats", {}) or {}
    categorical_summary = dataset_summary.get("categorical_summary", {}) or {}
    sample_rows = dataset_summary.get("sample_rows", []) or []

    compact_sample_rows = sample_rows[:2]

    return {
        "shape": dataset_summary.get("shape", {}),
        "columns": dataset_summary.get("columns", []),
        "dtypes": dataset_summary.get("dtypes", {}),
        "column_roles": dataset_summary.get("column_roles", {}),

        # Predicted target info
        "predicted_target_column": dataset_summary.get("target_column"),
        "target_confidence": dataset_summary.get("target_confidence"),
        "target_reason": dataset_summary.get("target_reason"),
        "top_target_candidates": dataset_summary.get(
            "target_candidates",
            []
        )[:5],

        # Data quality
        "missing_values": dataset_summary.get("missing_values", {}),
        "duplicate_rows": dataset_summary.get("duplicate_rows", 0),
        "memory_usage_kb": dataset_summary.get("memory_usage_kb", 0),
        "column_count_by_type": dataset_summary.get(
            "column_count_by_type",
            {}
        ),

        # Compact stats
        "numeric_stats": _limit_dict_items(
            numeric_stats,
            limit=8
        ),

        "categorical_summary": _limit_dict_items(
            categorical_summary,
            limit=8
        ),

        # Small preview only
        "sample_rows": compact_sample_rows,
    }


def _build_system_prompt(question: str) -> str:

    if _is_report_request(question):
        return """
You are a senior data analyst.

You will receive:
1. USER QUESTION
2. DATASET PROFILE

Rules:
- Use only the provided dataset profile.
- Never invent values.
- Never invent columns.
- Use predicted_target_column as target prediction.
- If confidence is low, mention it should be confirmed.
- Keep English simple and professional.

For report requests use this structure:

EXECUTIVE SUMMARY
[2 short paragraphs]

DATASET HEALTH
- [point]
- [point]

TARGET COLUMN
- Predicted target:
- Confidence:
- Reason:

KEY FINDINGS
- [point]
- [point]

IMPORTANT COLUMNS
- [point]
- [point]

WEAK OR LESS USEFUL COLUMNS
- [point]
- [point]

RECOMMENDATIONS
1. [recommendation]
2. [recommendation]
3. [recommendation]
"""

    return """
You are a senior data analyst.

You will receive:
1. USER QUESTION
2. DATASET PROFILE

Rules:
- Use only dataset profile.
- Never invent values.
- Never invent columns.
- Keep answer short and practical.
- Use predicted_target_column for target questions.
- If confidence is low, mention confirmation needed.
- Explain important/unimportant columns clearly.
- Do not generate code unless user asks.
"""


def analyze_text(
    user_question: str,
    dataset_summary: dict,
    chat_history: list | None = None,
) -> str:

    dataset_context = _build_compact_dataset_context(
        dataset_summary or {}
    )

    client = get_openai_client()
    model = get_openai_model()

    messages = [
        {
            "role": "system",
            "content": _build_system_prompt(user_question),
        },
        {
            "role": "system",
            "content":
                "DATASET PROFILE:\n"
                + _safe_json(dataset_context),
        },
    ]

    # Small history only
    if chat_history:
        for turn in chat_history[-2:]:

            role = turn.get("role", "user")

            content = str(
                turn.get("content", "")
            ).strip()

            if content:
                messages.append(
                    {
                        "role": role,
                        "content": content,
                    }
                )

    messages.append(
        {
            "role": "user",
            "content": user_question,
        }
    )

    # Only last few messages
    compact_messages = messages[-3:]

    response = client.invoke(compact_messages)

    return response.content.strip()


def text_analysis_node(
    state: AnalystState
) -> AnalystState:

    if state.get("error"):
        return state

    try:

        response = analyze_text(
            user_question=state.get(
                "user_question",
                ""
            ),

            dataset_summary=state.get(
                "dataset_summary",
                {}
            ),

            chat_history=state.get(
                "chat_history",
                []
            ),
        )

        return {
            **state,
            "text_response": response,
        }

    except Exception as exc:

        return {
            **state,
            "error": (
                f"Text analysis failed: {str(exc)}"
            ),
        }