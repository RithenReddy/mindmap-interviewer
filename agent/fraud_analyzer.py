from __future__ import annotations

import re
from typing import Any


SUSPICIOUS_PHRASES = [
    "as an ai language model",
    "here's a polished answer",
    "let me provide a comprehensive response",
    "in conclusion,",
]


def _token_set(text: str) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return {token for token in cleaned.split() if len(token) > 2}


def _jaccard_similarity(a: str, b: str) -> float:
    sa = _token_set(a)
    sb = _token_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa.intersection(sb)) / len(sa.union(sb))


def analyze_response_integrity(
    response_text: str,
    telemetry: dict[str, Any] | None,
    prior_responses: list[str] | None = None,
) -> dict:
    text = (response_text or "").strip()
    prior = prior_responses or []
    t = telemetry or {}
    char_count = int(t.get("char_count") or len(text))
    key_count = int(t.get("key_count") or 0)
    paste_count = int(t.get("paste_count") or 0)
    pasted_chars = int(t.get("pasted_chars") or 0)
    typing_duration_ms = int(t.get("typing_duration_ms") or 0)
    response_latency_ms = int(t.get("response_latency_ms") or 0)
    avg_inter_key_ms = float(t.get("avg_inter_key_ms") or 0.0)

    flags: list[str] = []
    score = 0.0

    paste_ratio = (pasted_chars / char_count) if char_count > 0 else 0.0
    if paste_count > 0 and paste_ratio >= 0.45 and char_count >= 80:
        flags.append("high_paste_ratio")
        score += 0.36
    elif paste_count > 0 and paste_ratio >= 0.2 and char_count >= 60:
        flags.append("moderate_paste_ratio")
        score += 0.18

    if typing_duration_ms > 0 and char_count >= 120:
        chars_per_sec = char_count / max(typing_duration_ms / 1000.0, 0.1)
        if chars_per_sec > 18:
            flags.append("unnaturally_fast_typing")
            score += 0.28
        elif chars_per_sec > 13:
            flags.append("very_fast_typing")
            score += 0.14

    if response_latency_ms > 0 and response_latency_ms < 1800 and char_count >= 160:
        flags.append("rapid_long_response")
        score += 0.22

    if avg_inter_key_ms > 0 and avg_inter_key_ms < 35 and key_count >= 60:
        flags.append("burst_input_pattern")
        score += 0.1

    lowered = text.lower()
    if any(phrase in lowered for phrase in SUSPICIOUS_PHRASES):
        flags.append("template_or_llm_phrase")
        score += 0.24

    max_similarity = 0.0
    if text and prior:
        max_similarity = max(_jaccard_similarity(text, prev) for prev in prior if prev)
        if max_similarity >= 0.85 and len(text) >= 50:
            flags.append("high_repetition_across_turns")
            score += 0.32
        elif max_similarity >= 0.7 and len(text) >= 40:
            flags.append("moderate_repetition_across_turns")
            score += 0.18

    score = max(0.0, min(1.0, round(score, 2)))
    if score >= 0.7:
        level = "high"
    elif score >= 0.4:
        level = "medium"
    else:
        level = "low"

    return {
        "risk_score": score,
        "risk_level": level,
        "flags": flags,
        "metrics": {
            "char_count": char_count,
            "key_count": key_count,
            "paste_count": paste_count,
            "pasted_chars": pasted_chars,
            "paste_ratio": round(paste_ratio, 2),
            "typing_duration_ms": typing_duration_ms,
            "response_latency_ms": response_latency_ms,
            "avg_inter_key_ms": round(avg_inter_key_ms, 2),
            "max_similarity_to_prior": round(max_similarity, 2),
        },
    }
