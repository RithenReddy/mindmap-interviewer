from __future__ import annotations

import os
from datetime import datetime, timezone


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def build_company_context_pack(
    *,
    interview_domain: str,
    job_description: str,
    candidate_context: str,
) -> dict:
    """
    Build a context pack that can be injected into interview reasoning.
    This intentionally supports mock mode for demo reliability when no Slack
    integration is configured.
    """
    enabled = os.getenv("ENABLE_SLACK_CONTEXT", "1").strip() == "1"
    mode = os.getenv("SLACK_CONTEXT_MODE", "mock").strip().lower() or "mock"
    channels = [c.strip() for c in os.getenv("SLACK_CONTEXT_CHANNELS", "").split(",") if c.strip()]

    if not enabled:
        return {
            "enabled": False,
            "source": "slack",
            "mode": "disabled",
            "used": False,
            "status": "Slack connector disabled by feature flag.",
            "signals": [],
            "summary": "",
            "generated_at": _utc_now(),
        }

    if mode == "mock":
        domain_hint = "delivery quality and execution trade-offs"
        if interview_domain == "consulting":
            domain_hint = "structured reasoning and stakeholder influence"
        elif interview_domain == "software_engineering":
            domain_hint = "system design depth and debugging discipline"

        summary = (
            "Slack context pack (mock): recent internal discussions emphasize "
            f"{domain_hint}. Focus interview probes on measurable impact, "
            "decision rationale, and cross-functional collaboration."
        )
        return {
            "enabled": True,
            "source": "slack",
            "mode": "mock",
            "used": True,
            "status": "Mock Slack context active (no external API call).",
            "signals": [
                {"label": "connector", "value": "slack"},
                {"label": "mode", "value": "mock"},
                {"label": "channels", "value": ", ".join(channels) if channels else "n/a"},
                {"label": "domain", "value": interview_domain},
                {"label": "job_chars", "value": str(len(job_description or ""))},
                {"label": "candidate_chars", "value": str(len(candidate_context or ""))},
            ],
            "summary": summary,
            "generated_at": _utc_now(),
        }

    return {
        "enabled": True,
        "source": "slack",
        "mode": mode,
        "used": False,
        "status": "Live Slack mode requested but not implemented in this build.",
        "signals": [{"label": "mode", "value": mode}],
        "summary": "",
        "generated_at": _utc_now(),
    }
