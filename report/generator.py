from __future__ import annotations

import json
import os
import time
import base64
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from agent.prompts import REPORT_PROMPT


DEFAULT_GUMLOOP_REPORT_URL = (
    "https://api.gumloop.com/api/v1/start_pipeline"
    "?user_id=hx5C9Y6io9enVlAg3TKHaB2gdvJ3&saved_item_id=exePwBLecjKvLGh6REdsZ7"
)
DEFAULT_GUMLOOP_REPORT_AGENT_ID = "kYucfzLJ87YexD8e6vjRPy"
REPORT_SCHEMA_TEMPLATE = {
    "overall_assessment": "",
    "score_snapshot": {
        "concept_coverage": "",
        "average_depth": "",
        "average_confidence": "",
        "signal_quality": "",
    },
    "concept_matrix": [],
    "strengths": [],
    "gaps": [],
    "follow_ups": [],
    "recommendation": {"decision": "", "confidence": "", "rationale": ""},
}


def _extract_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in [
            "report",
            "output",
            "result",
            "text",
            "content",
            "final_report",
            "markdown",
            "response",
        ]:
            inner = value.get(key)
            text = _extract_text(inner)
            if text:
                return text
        try:
            return json.dumps(value, indent=2)[:3000]
        except Exception:
            return str(value)[:3000]
    if isinstance(value, list):
        chunks = [_extract_text(item) for item in value]
        merged = "\n".join(chunk for chunk in chunks if chunk)
        return merged.strip()
    return ""


def _extract_json_object_from_text(text: str) -> dict | None:
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _normalize_list_of_dicts(value: Any, keys: list[str]) -> list[dict]:
    if not isinstance(value, list):
        return []
    out: list[dict] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        normalized = {key: str(item.get(key, "")).strip() for key in keys}
        if any(normalized.values()):
            out.append(normalized)
    return out


def _normalize_report_json(value: dict | None) -> dict:
    if not isinstance(value, dict):
        value = {}
    normalized = json.loads(json.dumps(REPORT_SCHEMA_TEMPLATE))
    normalized["overall_assessment"] = str(value.get("overall_assessment", "")).strip()

    score = value.get("score_snapshot", {})
    if isinstance(score, dict):
        normalized["score_snapshot"]["concept_coverage"] = str(
            score.get("concept_coverage", "")
        ).strip()
        normalized["score_snapshot"]["average_depth"] = str(score.get("average_depth", "")).strip()
        normalized["score_snapshot"]["average_confidence"] = str(
            score.get("average_confidence", "")
        ).strip()
        normalized["score_snapshot"]["signal_quality"] = str(score.get("signal_quality", "")).strip()

    normalized["concept_matrix"] = _normalize_list_of_dicts(
        value.get("concept_matrix"),
        ["concept", "depth", "confidence", "evidence", "verdict"],
    )
    normalized["strengths"] = [
        str(item).strip() for item in value.get("strengths", []) if str(item).strip()
    ]
    normalized["gaps"] = [str(item).strip() for item in value.get("gaps", []) if str(item).strip()]
    normalized["follow_ups"] = [
        str(item).strip() for item in value.get("follow_ups", []) if str(item).strip()
    ]

    rec = value.get("recommendation", {})
    if isinstance(rec, dict):
        normalized["recommendation"]["decision"] = str(rec.get("decision", "")).strip()
        normalized["recommendation"]["confidence"] = str(rec.get("confidence", "")).strip()
        normalized["recommendation"]["rationale"] = str(rec.get("rationale", "")).strip()
    return normalized


def _report_json_to_markdown(report_json: dict) -> str:
    assessment = report_json.get("overall_assessment", "")
    score = report_json.get("score_snapshot", {})
    matrix = report_json.get("concept_matrix", [])
    strengths = report_json.get("strengths", [])
    gaps = report_json.get("gaps", [])
    follow_ups = report_json.get("follow_ups", [])
    recommendation = report_json.get("recommendation", {})

    lines = [
        "# Interview Evaluation Report",
        "",
        "## Overall Assessment",
        assessment or "Not provided.",
        "",
        "## Score Snapshot",
        "| Metric | Value |",
        "|---|---|",
        f"| Concept Coverage | {score.get('concept_coverage', 'N/A')} |",
        f"| Average Depth | {score.get('average_depth', 'N/A')} |",
        f"| Average Confidence | {score.get('average_confidence', 'N/A')} |",
        f"| Signal Quality | {score.get('signal_quality', 'N/A')} |",
        "",
        "## Concept Evidence Matrix",
        "| Concept | Depth | Confidence | Evidence | Verdict |",
        "|---|---:|---|---|---|",
    ]
    for row in matrix:
        lines.append(
            f"| {row.get('concept','')} | {row.get('depth','')} | {row.get('confidence','')} | "
            f"{row.get('evidence','')} | {row.get('verdict','')} |"
        )
    lines.append("")
    lines.append("## Strengths")
    lines.extend([f"- {item}" for item in strengths] or ["- Not provided."])
    lines.append("")
    lines.append("## Gaps")
    lines.extend([f"- {item}" for item in gaps] or ["- Not provided."])
    lines.append("")
    lines.append("## Follow-up Questions")
    lines.extend([f"- {item}" for item in follow_ups] or ["- Not provided."])
    lines.append("")
    lines.append("## Recommendation")
    lines.append(
        f"**Decision:** {recommendation.get('decision', 'N/A')}  \n"
        f"**Confidence:** {recommendation.get('confidence', 'N/A')}  \n"
        f"{recommendation.get('rationale', '')}"
    )
    return "\n".join(lines).strip()


def _gumloop_user_id_from_token(token: str) -> str:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return ""
        payload = parts[1]
        padding = "=" * ((4 - len(payload) % 4) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload + padding))
        sub = data.get("sub")
        return str(sub).strip() if isinstance(sub, str) else ""
    except Exception:
        return ""


def _gumloop_candidate_endpoints(token: str) -> list[str]:
    explicit = os.getenv("GUMLOOP_REPORT_PIPELINE_URL", "").strip()
    if explicit:
        return [explicit]
    user_id = _gumloop_user_id_from_token(token)
    agent_id = os.getenv("GUMLOOP_REPORT_AGENT_ID", DEFAULT_GUMLOOP_REPORT_AGENT_ID).strip()
    urls: list[str] = []
    if user_id and agent_id:
        urls.append(
            "https://api.gumloop.com/api/v1/start_pipeline"
            f"?user_id={user_id}&saved_item_id={agent_id}"
        )
    urls.append(DEFAULT_GUMLOOP_REPORT_URL)
    # de-duplicate preserving order
    unique = []
    seen = set()
    for item in urls:
        if item not in seen:
            unique.append(item)
            seen.add(item)
    return unique


def _query_value(endpoint: str, key: str) -> str:
    try:
        parsed = urlparse(endpoint)
        values = parse_qs(parsed.query).get(key, [])
        return (values[0] if values else "").strip()
    except Exception:
        return ""


def _poll_pipeline_run(endpoint: str, run_id: str, timeout_seconds: int = 120) -> tuple[dict, str]:
    api_key = _query_value(endpoint, "api_key")
    user_id = _query_value(endpoint, "user_id")
    project_id = _query_value(endpoint, "project_id")
    if not api_key:
        return {}, "missing_api_key_in_pipeline_url"
    started = time.time()
    last_state = "UNKNOWN"
    while time.time() - started < timeout_seconds:
        params = {"api_key": api_key, "run_id": run_id}
        if user_id:
            params["user_id"] = user_id
        if project_id:
            params["project_id"] = project_id
        try:
            response = requests.get("https://api.gumloop.com/api/v1/get_pl_run", params=params, timeout=30)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return {}, str(exc)
        state = str(payload.get("state", "UNKNOWN")).upper()
        last_state = state
        if state in {"DONE", "FAILED", "TERMINATED"}:
            return payload if isinstance(payload, dict) else {}, state
        time.sleep(2)
    return {}, f"timeout_{last_state}"


def _call_gumloop_pipeline_webhook(endpoint: str, payload: dict) -> tuple[str, str]:
    candidate_bodies = [
        {"inputs": payload},
        {"input": payload},
        {
            "pipeline_inputs": [
                {"input_name": "inputs", "value": payload},
                {"input_name": "input", "value": payload},
                {"input_name": "payload", "value": payload},
            ]
        },
        payload,
        {},
    ]
    last_error = ""
    for body in candidate_bodies:
        try:
            start = requests.post(
                endpoint,
                headers={"Content-Type": "application/json"},
                json=body,
                timeout=35,
            )
            start.raise_for_status()
            started = start.json()
            run_id = str(started.get("run_id", "")).strip()
            if not run_id:
                continue
            final_run, state_or_error = _poll_pipeline_run(endpoint, run_id)
            if not final_run:
                last_error = state_or_error
                continue
            # Prefer outputs; fall back to full run/log text extraction.
            outputs_text = _extract_text(final_run.get("outputs", {}))
            if outputs_text:
                return outputs_text, f"pipeline_run:{run_id}:{state_or_error}"
            run_text = _extract_text(final_run)
            if run_text:
                return run_text, f"pipeline_run:{run_id}:{state_or_error}"
            last_error = state_or_error
        except Exception as exc:
            last_error = str(exc)
            continue
    return "", last_error or "pipeline_webhook_failed"


def _call_gumloop_agent(payload: dict) -> tuple[str, str]:
    api_key = os.getenv("GUMLOOP_API_KEY", "").strip()
    user_id = os.getenv("GUMLOOP_USER_ID", "").strip() or _query_value(DEFAULT_GUMLOOP_REPORT_URL, "user_id")
    agent_id = os.getenv("GUMLOOP_REPORT_AGENT_ID", DEFAULT_GUMLOOP_REPORT_AGENT_ID).strip()
    if not api_key or not user_id or not agent_id:
        return "", "missing_agent_api_settings"

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    message = (
        "Return ONLY JSON with keys overall_assessment, score_snapshot, concept_matrix, strengths, gaps, "
        "follow_ups, recommendation.\n\n"
        f"context={json.dumps(payload, ensure_ascii=True)}"
    )
    try:
        start = requests.post(
            "https://api.gumloop.com/api/v1/start_agent",
            headers=headers,
            json={"gummie_id": agent_id, "message": message, "user_id": user_id},
            timeout=45,
        )
        start.raise_for_status()
        interaction_id = str(start.json().get("interaction_id", "")).strip()
        if not interaction_id:
            return "", "missing_interaction_id"
    except Exception as exc:
        return "", str(exc)

    started_at = time.time()
    while time.time() - started_at < 140:
        time.sleep(2)
        try:
            status = requests.get(
                f"https://api.gumloop.com/api/v1/agent_status/{interaction_id}",
                headers={"Authorization": f"Bearer {api_key}"},
                params={"user_id": user_id},
                timeout=45,
            )
            status.raise_for_status()
            body = status.json()
        except Exception as exc:
            return "", str(exc)

        state = str(body.get("state", "")).upper()
        if state == "COMPLETED":
            response_text = _extract_text(body.get("response"))
            if response_text:
                return response_text, f"agent_interaction:{interaction_id}"
            messages_text = _extract_text(body.get("messages"))
            return messages_text, f"agent_interaction:{interaction_id}"
        if state == "FAILED":
            return "", str(body.get("error_message", "agent_failed"))
    return "", "agent_timeout"


def _call_gumloop_report(payload: dict) -> tuple[str, str]:
    agent_text, agent_meta = _call_gumloop_agent(payload)
    if agent_text:
        return agent_text, agent_meta

    explicit_endpoint = os.getenv("GUMLOOP_REPORT_PIPELINE_URL", "").strip()
    if explicit_endpoint and "api_key=" in explicit_endpoint and "/start_pipeline" in explicit_endpoint:
        return _call_gumloop_pipeline_webhook(explicit_endpoint, payload)

    token = os.getenv("GUMLOOP_MCP_TOKEN", "").strip()
    if not token:
        return "", "missing_token"
    endpoints = _gumloop_candidate_endpoints(token)
    if not endpoints:
        return "", "missing_endpoint"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    candidate_bodies = [
        {"inputs": payload},
        {"input": payload},
        payload,
    ]
    last_error = ""
    for endpoint in endpoints:
        for body in candidate_bodies:
            try:
                response = requests.post(endpoint, headers=headers, json=body, timeout=35)
                response.raise_for_status()
                result = response.json()
                text = _extract_text(result)
                if text:
                    return text, endpoint
            except Exception as exc:
                last_error = str(exc)
                continue
    return "", last_error or "unknown_error"


def _call_anthropic_report(prompt: str) -> tuple[str, str]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return "", "missing_anthropic_key"

    try:
        from anthropic import Anthropic
    except Exception as exc:
        return "", f"anthropic_import_failed:{exc}"

    client = Anthropic(api_key=api_key)
    schema_hint = json.dumps(REPORT_SCHEMA_TEMPLATE, ensure_ascii=True)
    models = [
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-haiku-20240307",
    ]
    last_error = ""
    for model in models:
        try:
            response = client.messages.create(
                model=model,
                max_tokens=1600,
                temperature=0.2,
                system=(
                    "You are an interview evaluator. Return ONLY valid JSON."
                    " Do not include markdown fences."
                    f" JSON schema: {schema_hint}"
                ),
                messages=[{"role": "user", "content": prompt}],
            )
            text_blocks = [
                block.text for block in response.content if getattr(block, "type", "") == "text"
            ]
            text = "\n".join(text_blocks).strip()
            if text:
                return text, f"anthropic_model:{model}"
            last_error = f"empty_response:{model}"
        except Exception as exc:
            last_error = f"{model}:{exc}"
            continue
    return "", last_error or "anthropic_unknown_error"


def _coerce_to_report_json(agent, raw_report: str) -> dict:
    parsed = _extract_json_object_from_text(raw_report)
    if parsed:
        return _normalize_report_json(parsed)
    return _normalize_report_json(None)


def _matrix_row_is_placeholder(row: dict) -> bool:
    concept = str(row.get("concept", "")).strip().lower()
    evidence = str(row.get("evidence", "")).strip().lower()
    if concept in {"", "-", "n/a", "none", "null"}:
        return True
    if evidence in {"", "-", "n/a", "none", "null", "unexplored"}:
        return True
    return False


def _repair_report_json(agent, report_json: dict) -> dict:
    repaired = _normalize_report_json(report_json)
    fallback = _local_template_report(agent, "")
    fallback_matrix = fallback.get("concept_matrix", [])
    current_matrix = repaired.get("concept_matrix", [])
    placeholder_count = sum(1 for row in current_matrix if isinstance(row, dict) and _matrix_row_is_placeholder(row))
    matrix_is_poor = (
        not isinstance(current_matrix, list)
        or not current_matrix
        or placeholder_count >= max(2, int(len(current_matrix) * 0.5))
    )

    if matrix_is_poor and fallback_matrix:
        repaired["concept_matrix"] = fallback_matrix
    elif isinstance(current_matrix, list) and fallback_matrix:
        enriched_matrix: list[dict] = []
        for idx, row in enumerate(current_matrix):
            if not isinstance(row, dict):
                row = {}
            fallback_row = fallback_matrix[idx] if idx < len(fallback_matrix) else {}
            concept_val = str(row.get("concept", "")).strip()
            depth_val = str(row.get("depth", "")).strip()
            confidence_val = str(row.get("confidence", "")).strip()
            verdict_val = str(row.get("verdict", "")).strip()
            if concept_val in {"", "-", "n/a", "none", "null"}:
                row["concept"] = fallback_row.get("concept", "")
            if depth_val in {"", "-", "n/a", "none", "null"}:
                row["depth"] = fallback_row.get("depth", "")
            if confidence_val in {"", "-", "none", "null"}:
                row["confidence"] = fallback_row.get("confidence", "")
            if verdict_val in {"", "-", "n/a", "none", "null"}:
                row["verdict"] = fallback_row.get("verdict", "")
            if not str(row.get("evidence", "")).strip():
                row["evidence"] = fallback_row.get("evidence", "")
            enriched_matrix.append(row)
        repaired["concept_matrix"] = _normalize_list_of_dicts(
            enriched_matrix, ["concept", "depth", "confidence", "evidence", "verdict"]
        )

    snapshot = repaired.get("score_snapshot", {})
    fallback_snapshot = fallback.get("score_snapshot", {})
    for key in ["concept_coverage", "average_depth", "average_confidence", "signal_quality"]:
        if not str(snapshot.get(key, "")).strip():
            snapshot[key] = fallback_snapshot.get(key, "")
    repaired["score_snapshot"] = snapshot

    for key in ["strengths", "gaps", "follow_ups"]:
        values = repaired.get(key, [])
        if not isinstance(values, list) or not any(str(item).strip() for item in values):
            repaired[key] = fallback.get(key, [])

    rec = repaired.get("recommendation", {})
    fallback_rec = fallback.get("recommendation", {})
    for key in ["decision", "confidence", "rationale"]:
        if not str(rec.get(key, "")).strip():
            rec[key] = fallback_rec.get(key, "")
    repaired["recommendation"] = rec

    if not str(repaired.get("overall_assessment", "")).strip():
        repaired["overall_assessment"] = fallback.get("overall_assessment", "")
    return repaired


def _local_template_report(agent, fallback_reason: str = "") -> dict:
    concepts = list(agent.graph.concepts.values())
    if concepts:
        covered = sum(1 for concept in concepts if concept.depth_score > 0)
        avg_depth = round(sum(concept.depth_score for concept in concepts) / len(concepts), 2)
    else:
        covered = 0
        avg_depth = 0.0
    confidence_values: list[float] = []
    matrix: list[dict] = []
    for concept in sorted(concepts, key=lambda c: c.depth_score, reverse=True)[:12]:
        evidence = ""
        confidence_text = ""
        for turn in reversed(agent.session_data):
            for assessed in turn.get("concepts_assessed", []):
                if isinstance(assessed, dict) and assessed.get("concept_id") == concept.id:
                    evidence = str(assessed.get("evidence", "")).strip()
                    conf = assessed.get("confidence_score")
                    band = str(assessed.get("confidence_band", "")).strip()
                    if isinstance(conf, (int, float)):
                        confidence_values.append(float(conf))
                        confidence_text = f"{band or 'scored'} ({round(float(conf), 2)})"
                    break
            if evidence:
                break
        matrix.append(
            {
                "concept": concept.name or concept.id,
                "depth": str(concept.depth_score),
                "confidence": confidence_text or "n/a",
                "evidence": evidence or "Insufficient evidence",
                "verdict": (
                    "strong"
                    if concept.depth_score >= 3
                    else "partial"
                    if concept.depth_score == 2
                    else "weak"
                    if concept.depth_score == 1
                    else "unexplored"
                ),
            }
        )
    avg_conf = round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.0
    strengths = [f"{row['concept']}: {row['evidence']}" for row in matrix if row["verdict"] == "strong"][:4]
    gaps = [f"{row['concept']} needs deeper validation." for row in matrix if row["verdict"] in {"weak", "unexplored"}][:5]
    follow_ups = [
        "Describe one high-stakes decision you made and what data changed your view.",
        "What trade-off did you accept, and why was it worth it?",
        "Which assumption in your previous answer is most likely to fail?",
    ]
    decision = "hold" if avg_depth >= 1.5 else "reject"
    signal = "high" if avg_depth >= 2.2 else "medium" if avg_depth >= 1.3 else "low"
    return _normalize_report_json(
        {
            "overall_assessment": (
                f"Generated via local fallback because Gumloop report paths were unavailable. "
                f"{fallback_reason[:220]}"
            ),
            "score_snapshot": {
                "concept_coverage": f"{covered}/{len(concepts)}",
                "average_depth": str(avg_depth),
                "average_confidence": str(avg_conf),
                "signal_quality": signal,
            },
            "concept_matrix": matrix,
            "strengths": strengths or ["No strong areas confirmed from available evidence."],
            "gaps": gaps or ["No major gaps detected, but evidence is limited."],
            "follow_ups": follow_ups,
            "recommendation": {
                "decision": decision,
                "confidence": "low",
                "rationale": "Use Gumloop agent output once available for final decision quality.",
            },
        }
    )


def generate_report(agent) -> dict:
    prompt = REPORT_PROMPT.format(
        role_title=agent.role_title,
        experience_level=agent.experience_level,
        interview_domain=agent.interview_domain,
        candidate_context=agent.candidate_context or "Not provided.",
        final_graph_state=agent.graph.get_state_summary(),
        session_data=json.dumps(agent.session_data, indent=2),
    )

    payload = {
        "role_title": agent.role_title,
        "experience_level": agent.experience_level,
        "interview_domain": agent.interview_domain,
        "candidate_context": agent.candidate_context or "Not provided.",
        "final_graph_state": agent.graph.get_state_summary(),
        "session_data": agent.session_data,
        "instruction_prompt": prompt,
        "requested_output_format": "json_report",
        "timestamp": int(time.time()),
    }
    gumloop_report, gumloop_meta = _call_gumloop_report(payload)
    if gumloop_report:
        report_json = _repair_report_json(agent, _coerce_to_report_json(agent, gumloop_report))
        if not report_json.get("overall_assessment"):
            report_json = _local_template_report(agent, "Gumloop returned non-JSON report payload.")
        return {
            "content": _report_json_to_markdown(report_json),
            "json": report_json,
            "source": "gumloop_pipeline",
            "meta": gumloop_meta,
        }

    anthropic_report, anthropic_meta = _call_anthropic_report(prompt)
    if anthropic_report:
        report_json = _repair_report_json(agent, _coerce_to_report_json(agent, anthropic_report))
        if report_json.get("overall_assessment"):
            return {
                "content": _report_json_to_markdown(report_json),
                "json": report_json,
                "source": "anthropic_fallback",
                "meta": anthropic_meta,
            }

    fallback_reason = "; ".join(
        part for part in [f"gumloop={gumloop_meta}", f"anthropic={anthropic_meta}"] if part
    )
    report_json = _local_template_report(agent, fallback_reason)
    return {
        "content": _report_json_to_markdown(report_json),
        "json": report_json,
        "source": "local_template_fallback",
        "meta": fallback_reason,
    }
