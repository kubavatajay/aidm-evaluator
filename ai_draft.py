"""AI-drafted competency assessment.

draft_assessment() asks Claude to propose a C/D/N rating and a short rationale
from the skill being assessed, the mentor's free-text note, and (optionally) the
captured photo. If no Anthropic API key is configured it falls back to a
transparent, deterministic heuristic so the app stays fully usable offline.

The mentor always reviews and can override the draft before it is saved — the
AI never has the final say.
"""

from __future__ import annotations

import json

from config import RATINGS, RATING_LABELS, RATING_DESCRIPTIONS

MODEL = "claude-opus-4-8"

_SCHEMA = {
    "type": "object",
    "properties": {
        "rating": {"type": "string", "enum": RATINGS},
        "rationale": {"type": "string"},
    },
    "required": ["rating", "rationale"],
    "additionalProperties": False,
}


def _api_key():
    """Resolve the Anthropic API key from Streamlit secrets or the env."""
    import os

    try:
        import streamlit as st
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass
    return os.environ.get("ANTHROPIC_API_KEY")


def is_live() -> bool:
    """True when a real Claude API call will be made."""
    return bool(_api_key())


def _system_prompt() -> str:
    levels = "\n".join(
        f"- {r} ({RATING_LABELS[r]}): {RATING_DESCRIPTIONS[r]}" for r in RATINGS
    )
    return (
        "You are an experienced clinical educator assisting a mentor who is "
        "assessing a resident on a single procedural skill during a bootcamp.\n\n"
        "Rate the resident's performance using exactly one of these levels:\n"
        f"{levels}\n\n"
        "Base your rating only on the evidence provided (the mentor's note and "
        "any photo). Be fair and specific. Write the rationale as 1-2 sentences "
        "addressed to the mentor, citing what in the evidence supports the level. "
        "If evidence is thin, say so and lean toward 'Developing'. This is a "
        "draft the mentor will review and may override."
    )


def _user_blocks(skill: str, note: str, photo_bytes: bytes | None) -> list:
    text = (
        f"Skill being assessed: {skill}\n\n"
        f"Mentor's observation note:\n{note.strip() or '(no note provided)'}\n\n"
        "Draft a rating and rationale."
    )
    blocks: list = []
    if photo_bytes:
        import base64

        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.b64encode(photo_bytes).decode("ascii"),
                },
            }
        )
    blocks.append({"type": "text", "text": text})
    return blocks


def _heuristic(skill: str, note: str) -> dict:
    """Deterministic fallback when no API key is available.

    Scans the note for cues. Transparent and good enough to demo the flow.
    """
    text = (note or "").lower()
    strong = (
        "independent", "independently", "confident", "smooth", "no prompt",
        "first attempt", "first pass", "excellent", "competent", "nailed",
        "without help", "unassisted", "correctly",
    )
    weak = (
        "struggled", "unable", "failed", "could not", "couldn't", "needs work",
        "repeat", "multiple attempts", "lots of prompting", "unsafe", "missed",
        "incorrect", "not yet", "difficulty",
    )
    mid = ("prompt", "guided", "with help", "assisted", "some", "improving",
           "progress", "partial", "coaching")

    score = sum(w in text for w in strong) - sum(w in text for w in weak)
    has_mid = any(w in text for w in mid)

    if score >= 1 and not has_mid:
        rating = "C"
    elif score <= -1:
        rating = "N"
    else:
        rating = "D"

    rationale = (
        f"(Simulated draft) Based on the note for '{skill}', the language "
        f"suggests {RATING_LABELS[rating].lower()} performance. Review the "
        "evidence and adjust if needed."
    )
    return {"rating": rating, "rationale": rationale}


def draft_assessment(skill: str, note: str, photo_bytes: bytes | None = None) -> dict:
    """Return {'rating': 'C'|'D'|'N', 'rationale': str, 'source': 'ai'|'simulated'}.

    Never raises: any API problem degrades gracefully to the heuristic.
    """
    key = _api_key()
    if not key:
        result = _heuristic(skill, note)
        result["source"] = "simulated"
        return result

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key)
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            thinking={"type": "adaptive"},
            system=_system_prompt(),
            messages=[{"role": "user", "content": _user_blocks(skill, note, photo_bytes)}],
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        data = json.loads(text)
        rating = data.get("rating")
        if rating not in RATINGS:
            raise ValueError(f"unexpected rating: {rating!r}")
        return {
            "rating": rating,
            "rationale": data.get("rationale", "").strip(),
            "source": "ai",
        }
    except Exception as exc:
        # Surface the failure in the rationale but keep the app moving.
        result = _heuristic(skill, note)
        result["rationale"] += f"  [AI draft unavailable: {exc}]"
        result["source"] = "simulated"
        return result
