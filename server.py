from __future__ import annotations

import base64
import concurrent.futures
import json
import os
import re
import time
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import requests

from agent.fraud_analyzer import analyze_response_integrity
from agent.gap_finder import suggest_next_gap
from agent.interviewer import InterviewAgent
from agent.onboarding_scraper import (
    FIRECRAWL_MCP_URL,
    GumloopMcpClient,
    scrape_onboarding_data,
)
from report.generator import generate_report
from context_connectors.slack import build_company_context_pack


class ScrapeRequest(BaseModel):
    linkedin_url: str = ""
    job_url: str = ""


class StartInterviewRequest(BaseModel):
    job_description: str = Field(min_length=20)
    experience_level: str
    interview_domain: str = "software_engineering"
    candidate_context: str = ""


class RespondRequest(BaseModel):
    session_id: str
    response: str = Field(min_length=1)
    telemetry: dict = Field(default_factory=dict)


app = FastAPI(title="MindMap Interviewer API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSIONS: dict[str, InterviewAgent] = {}
SESSION_META: dict[str, dict] = {}
SCRAPE_CACHE: dict[str, dict] = {}
ACTIVITY_LOG = deque(maxlen=160)
GUMLOOP_AUTH_BASE = "https://api.gumloop.com"
PROJECT_ROOT = Path(__file__).resolve().parent
GUMLOOP_TOKENS_PATH = PROJECT_ROOT / ".gumloop_tokens.json"
GUMLOOP_OAUTH_SESSION_PATH = PROJECT_ROOT / ".gumloop_oauth_session.json"
MAX_QUESTION_COUNT = 8

DEMO_JOB_DESCRIPTION = """Head of Marketing at Gumloop (sample demo fallback)

Responsibilities:
- Own positioning, demand generation, and PLG growth loops
- Launch experiments across paid + organic channels
- Translate technical product capabilities into crisp business value

Interview focus:
- Strategic prioritization under ambiguity
- Experiment design and measurement rigor
- Cross-functional leadership with product/engineering
"""

DEMO_CANDIDATE_CONTEXT = """Candidate: Alex Morgan (demo profile)
- 4 years in B2B SaaS growth roles
- Led lifecycle experiments and product-led onboarding optimization
- Built experimentation dashboards with SQL + BI tools
- Strong on messaging and campaign operations; less exposure to enterprise sales motions
"""


def _require_anthropic_key() -> str:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured.")
    return key


def _resolve_interview_provider() -> tuple[str, str]:
    gumloop_api_key = os.getenv("GUMLOOP_API_KEY", "").strip()
    gumloop_user_id = os.getenv("GUMLOOP_USER_ID", "").strip()
    gumloop_agent_id = os.getenv("GUMLOOP_INTERVIEW_AGENT_ID", "").strip() or os.getenv(
        "GUMLOOP_REPORT_AGENT_ID", ""
    ).strip()
    if gumloop_api_key and gumloop_user_id and gumloop_agent_id:
        return "gumloop", gumloop_api_key
    return "anthropic", _require_anthropic_key()


def _safe_read_json_file(path: Path) -> dict:
    try:
        if not path.exists():
            return {}
        parsed = json.loads(path.read_text())
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _safe_write_json_file(path: Path, payload: dict) -> None:
    try:
        path.write_text(json.dumps(payload, indent=2))
    except Exception:
        pass


def _jwt_expiry_epoch(token: str) -> int | None:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1]
        padding = "=" * ((4 - (len(payload) % 4)) % 4)
        decoded = base64.urlsafe_b64decode(payload + padding)
        data = json.loads(decoded)
        exp = data.get("exp")
        return int(exp) if isinstance(exp, (int, float)) else None
    except Exception:
        return None


def _is_token_expired(token: str, leeway_seconds: int = 60) -> bool:
    exp = _jwt_expiry_epoch((token or "").strip())
    if exp is None:
        return True
    return int(time.time()) >= int(exp) - leeway_seconds


def _refresh_gumloop_access_token() -> str:
    tokens = _safe_read_json_file(GUMLOOP_TOKENS_PATH)
    oauth = _safe_read_json_file(GUMLOOP_OAUTH_SESSION_PATH)
    refresh_token = str(tokens.get("refresh_token", "")).strip()
    client_id = str(oauth.get("client_id", "")).strip()
    if not refresh_token or not client_id:
        return ""

    try:
        response = requests.post(
            f"{GUMLOOP_AUTH_BASE}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": refresh_token,
            },
            timeout=20,
        )
        response.raise_for_status()
        body = response.json()
    except Exception:
        return ""

    new_access_token = str(body.get("access_token", "")).strip()
    if not new_access_token:
        return ""
    _safe_write_json_file(GUMLOOP_TOKENS_PATH, body if isinstance(body, dict) else tokens)
    os.environ["GUMLOOP_MCP_TOKEN"] = new_access_token
    return new_access_token


def _resolve_gumloop_token() -> str:
    env_token = os.getenv("GUMLOOP_MCP_TOKEN", "").strip()
    if env_token and not _is_token_expired(env_token):
        return env_token

    file_tokens = _safe_read_json_file(GUMLOOP_TOKENS_PATH)
    file_token = str(file_tokens.get("access_token", "")).strip()
    if file_token and not _is_token_expired(file_token):
        os.environ["GUMLOOP_MCP_TOKEN"] = file_token
        return file_token

    refreshed_token = _refresh_gumloop_access_token()
    if refreshed_token:
        return refreshed_token
    return env_token or file_token


def _cache_key(linkedin_url: str, job_url: str) -> str:
    return f"{linkedin_url.strip()}|{job_url.strip()}".lower()


def _strip_html(value: str) -> str:
    text = re.sub(r"<script.*?>.*?</script>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style.*?>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _direct_fetch_text(url: str, max_chars: int = 6000) -> str:
    if not url.strip():
        return ""
    response = requests.get(
        url.strip(),
        headers={"User-Agent": "Mozilla/5.0 MindMapInterviewer/1.0"},
        timeout=15,
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    body = response.text or ""
    if "html" in content_type.lower():
        body = _strip_html(body)
    return body[:max_chars].strip()


def _fetch_parallel_context(
    token: str,
    interview_domain: str,
    role_title: str,
    target_concept_name: str,
    candidate_response: str,
) -> dict:
    if not token.strip():
        return {"used": False, "summary": "", "source": "none", "error": "No Gumloop token."}
    query = (
        f"{interview_domain} interview rubric for {role_title}; "
        f"concept: {target_concept_name}; candidate signal: {candidate_response[:200]}"
    )
    try:
        client = GumloopMcpClient(token)
        tools = client.list_tools(FIRECRAWL_MCP_URL)
        tool_names = [str(tool.get("name", "")) for tool in tools]
        preferred = "search" if "search" in tool_names else ("scrape" if "scrape" in tool_names else "")
        if not preferred:
            return {
                "used": False,
                "summary": "",
                "source": "none",
                "error": "No Firecrawl tool available for enrichment.",
            }
        if preferred == "search":
            result = client.call_tool(
                FIRECRAWL_MCP_URL,
                "search",
                {"query": query, "limit": 3, "scrapeOptions": {"formats": [{"type": "summary"}]}},
            )
        else:
            result = client.call_tool(
                FIRECRAWL_MCP_URL,
                "scrape",
                {
                    "url": "https://www.manager-tools.com/2005/10/behavioral-interviewing-questions",
                    "formats": [{"type": "summary"}],
                },
            )
        payload = json.dumps(result)
        summary = payload[:1200].strip()
        if not summary:
            return {"used": False, "summary": "", "source": preferred, "error": "Empty enrichment."}
        return {"used": True, "summary": summary, "source": preferred, "error": ""}
    except Exception as exc:
        return {"used": False, "summary": "", "source": "firecrawl", "error": str(exc)}


def _concept_confidence_band(depth_score: int, evidence: str) -> tuple[float, str]:
    score = 0.35
    score += min(max(depth_score, 0), 3) * 0.18
    if evidence and len(evidence.strip()) >= 20:
        score += 0.14
    score = min(0.96, max(0.05, score))
    if score >= 0.75:
        return score, "high"
    if score >= 0.5:
        return score, "medium"
    return score, "low"


def _compute_session_metrics(agent: InterviewAgent) -> dict:
    concept_scores = [concept.depth_score for concept in agent.graph.concepts.values()]
    avg_depth = round(sum(concept_scores) / len(concept_scores), 2) if concept_scores else 0.0
    covered = sum(1 for value in concept_scores if value > 0)
    confidence_values = []
    for turn in agent.session_data:
        for item in turn.get("concepts_assessed", []):
            if isinstance(item, dict):
                val = item.get("confidence_score")
                if isinstance(val, (int, float)):
                    confidence_values.append(float(val))
    avg_conf = round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.0
    return {
        "avg_depth": avg_depth,
        "covered_concepts": covered,
        "total_concepts": len(concept_scores),
        "avg_confidence": avg_conf,
    }


def _compute_integrity_metrics(agent: InterviewAgent) -> dict:
    fraud_turns = []
    all_flags: dict[str, int] = {}
    for turn in agent.session_data:
        fraud = turn.get("fraud_analysis", {}) if isinstance(turn, dict) else {}
        if not isinstance(fraud, dict):
            continue
        score = fraud.get("risk_score")
        level = fraud.get("risk_level")
        if not isinstance(score, (int, float)):
            continue
        flags = fraud.get("flags", [])
        if isinstance(flags, list):
            for flag in flags:
                key = str(flag)
                all_flags[key] = all_flags.get(key, 0) + 1
        fraud_turns.append({"risk_score": float(score), "risk_level": str(level or "low"), "flags": flags})

    if not fraud_turns:
        return {
            "average_risk_score": 0.0,
            "max_risk_score": 0.0,
            "high_risk_turns": 0,
            "top_flags": [],
            "verdict": "No suspicious keyboard patterns detected.",
        }
    average = round(sum(t["risk_score"] for t in fraud_turns) / len(fraud_turns), 2)
    max_score = round(max(t["risk_score"] for t in fraud_turns), 2)
    high_risk_turns = sum(1 for t in fraud_turns if t["risk_score"] >= 0.7)
    top_flags = sorted(all_flags.items(), key=lambda item: item[1], reverse=True)[:5]
    top_flag_names = [name for name, _count in top_flags]
    if high_risk_turns >= 2 or max_score >= 0.85:
        verdict = "Escalate for manual review due to repeated suspicious typing signals."
    elif average >= 0.4:
        verdict = "Medium integrity risk. Validate with follow-up probing."
    else:
        verdict = "Low integrity risk from keyboard telemetry."
    return {
        "average_risk_score": average,
        "max_risk_score": max_score,
        "high_risk_turns": high_risk_turns,
        "top_flags": top_flag_names,
        "verdict": verdict,
    }


def _record_activity(
    method: str,
    path: str,
    status_code: int,
    elapsed_ms: int,
    note: str = "",
) -> None:
    ACTIVITY_LOG.appendleft(
        {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "method": method,
            "path": path,
            "status_code": status_code,
            "elapsed_ms": elapsed_ms,
            "note": note,
        }
    )


@app.middleware("http")
async def activity_middleware(request: Request, call_next):
    started = time.perf_counter()
    status_code = 500
    note = ""
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    except Exception as exc:
        note = str(exc)[:180]
        raise
    finally:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        _record_activity(request.method, request.url.path, status_code, elapsed_ms, note)


def _serialize_graph(agent: InterviewAgent) -> dict:
    nodes = [asdict(concept) for concept in agent.graph.concepts.values()]
    edges = [{"source": source, "target": target} for source, target in agent.graph.graph.edges()]
    return {"nodes": nodes, "edges": edges, "stats": agent.graph.get_stats()}


def _serialize_session(agent: InterviewAgent, session_id: str) -> dict:
    meta = SESSION_META.get(session_id, {}) if isinstance(SESSION_META.get(session_id, {}), dict) else {}
    return {
        "session_id": session_id,
        "role_title": agent.role_title,
        "experience_level": agent.experience_level,
        "interview_domain": agent.interview_domain,
        "session_complete": agent.session_complete,
        "last_target_concept": agent.last_target_concept,
        "graph": _serialize_graph(agent),
        "question_count": len(agent.session_data),
        "max_questions": MAX_QUESTION_COUNT,
        "metrics": _compute_session_metrics(agent),
        "context_signals": meta.get("context_signals", {}),
    }


def _safe_json_parse(value: str) -> dict | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_json_object(value: str) -> dict | None:
    parsed = _safe_json_parse(value)
    if parsed:
        return parsed
    if not isinstance(value, str):
        return None

    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        candidate = value[start : end + 1]
        parsed = _safe_json_parse(candidate)
        if parsed:
            return parsed
    return None


def _clean_job_description(raw_value: str) -> str:
    parsed = _safe_json_parse(raw_value)
    if not parsed:
        return raw_value.strip()
    markdown = parsed.get("markdown")
    if isinstance(markdown, str) and markdown.strip():
        return markdown.strip()
    metadata = parsed.get("metadata", {})
    if isinstance(metadata, dict):
        title = metadata.get("title")
        source = metadata.get("sourceURL") or metadata.get("url")
        status = metadata.get("statusCode")
        bits = [f"Title: {title}" if title else "", f"URL: {source}" if source else ""]
        if status:
            bits.append(f"Status Code: {status}")
        summary = "\n".join(bit for bit in bits if bit)
        if summary:
            return summary
    return raw_value.strip()


def _clean_candidate_context(raw_value: str) -> str:
    parsed = _safe_json_parse(raw_value)
    if not parsed:
        return raw_value.strip()
    person = parsed.get("person", {})
    if not isinstance(person, dict):
        return raw_value.strip()
    lines = []
    name = person.get("name") or "Unknown candidate"
    title = person.get("title")
    headline = person.get("headline")
    linkedin = person.get("linkedin_url")
    lines.append(f"Name: {name}")
    if title:
        lines.append(f"Title: {title}")
    if headline:
        lines.append(f"Headline: {headline}")
    if linkedin:
        lines.append(f"LinkedIn: {linkedin}")
    if person.get("employment_history"):
        lines.append("Employment history detected in profile.")
    return "\n".join(lines).strip()


def _scraped_job_content_only(raw_value: str) -> str:
    parsed = _safe_json_parse(raw_value)
    if not parsed:
        return raw_value.strip()
    markdown = parsed.get("markdown")
    if isinstance(markdown, str) and markdown.strip():
        return markdown.strip()
    return raw_value.strip()


def _scraped_candidate_content_only(raw_value: str) -> str:
    parsed = _safe_json_parse(raw_value)
    if not parsed:
        return raw_value.strip()
    person = parsed.get("person")
    if not isinstance(person, dict):
        return raw_value.strip()
    lines = []
    name = person.get("name") or "Not available from scraped profile"
    lines.append(f"Name: {name}")
    for label, key in [
        ("Title", "title"),
        ("Headline", "headline"),
        ("LinkedIn", "linkedin_url"),
        ("Email", "email"),
        ("Seniority", "seniority"),
    ]:
        value = person.get(key)
        if value:
            lines.append(f"{label}: {value}")
    employment = person.get("employment_history")
    if isinstance(employment, list) and employment:
        lines.append("Employment History:")
        for item in employment[:4]:
            if isinstance(item, dict):
                company = item.get("organization_name") or "Unknown organization"
                title = item.get("title") or "Unknown role"
                lines.append(f"- {title} @ {company}")
    return "\n".join(lines).strip()


def _format_scrape_with_haiku(
    raw_job: str, raw_candidate: str, linkedin_url: str, job_url: str
) -> dict | None:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        from anthropic import Anthropic
    except Exception:
        return None

    def _escape_format(value: str) -> str:
        return (value or "").replace("{", "{{").replace("}", "}}")

    prompt = ONBOARDING_PRESENTATION_PROMPT.format(
        linkedin_url=_escape_format(linkedin_url or "Not provided"),
        job_url=_escape_format(job_url or "Not provided"),
        raw_job_content=_escape_format(raw_job or "Not available"),
        raw_candidate_content=_escape_format(raw_candidate or "Not available"),
    )

    models = ["claude-3-haiku-20240307", "claude-3-5-haiku-20241022"]
    client = Anthropic(api_key=api_key)
    for model in models:
        try:
            response = client.messages.create(
                model=model,
                max_tokens=900,
                temperature=0.2,
                system=(
                    "Return only the requested tagged structure."
                    " Do not include markdown fences or any extra commentary."
                ),
                messages=[{"role": "user", "content": prompt}],
            )
            text_blocks = [
                block.text
                for block in response.content
                if getattr(block, "type", "") == "text"
            ]
            text = "\n".join(text_blocks).strip()
            parsed = _extract_json_object(text)
            if parsed and isinstance(parsed.get("job_description"), str) and isinstance(
                parsed.get("candidate_context"), str
            ):
                return {
                    "job_description": parsed["job_description"].strip(),
                    "candidate_context": parsed["candidate_context"].strip(),
                    "formatter_model": model,
                }

            job_match = re.search(
                r"<job_description>(.*?)</job_description>", text, flags=re.IGNORECASE | re.DOTALL
            )
            candidate_match = re.search(
                r"<candidate_context>(.*?)</candidate_context>",
                text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if job_match and candidate_match:
                return {
                    "job_description": job_match.group(1).strip(),
                    "candidate_context": candidate_match.group(1).strip(),
                    "formatter_model": model,
                }
        except Exception:
            continue
    return None


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "anthropic_configured": bool(os.getenv("ANTHROPIC_API_KEY")),
        "gumloop_configured": bool(os.getenv("GUMLOOP_MCP_TOKEN")),
        "gumloop_interview_configured": bool(os.getenv("GUMLOOP_API_KEY") and os.getenv("GUMLOOP_USER_ID")),
    }


@app.get("/api/activity")
def activity(limit: int = 40) -> dict:
    safe_limit = max(1, min(200, int(limit)))
    return {"ok": True, "events": list(ACTIVITY_LOG)[:safe_limit]}


@app.post("/api/onboarding/scrape")
def scrape_onboarding(payload: ScrapeRequest) -> dict:
    key = _cache_key(payload.linkedin_url, payload.job_url)
    try:
        gumloop_token = _resolve_gumloop_token()
        scraped = scrape_onboarding_data(
            linkedin_url=payload.linkedin_url,
            job_url=payload.job_url,
            gumloop_token=gumloop_token,
        )
        raw_job = scraped.get("job_description", "")
        raw_candidate = scraped.get("candidate_context", "")
        scraped["job_description_raw"] = raw_job
        scraped["candidate_context_raw"] = raw_candidate
        scraped["job_description"] = _scraped_job_content_only(raw_job)
        scraped["candidate_context"] = _scraped_candidate_content_only(raw_candidate)
        scraped["presentation_model"] = "scrape_only"
        scraped["reliability_mode"] = "live"
        if key:
            SCRAPE_CACHE[key] = scraped
        return {"ok": True, "data": scraped}
    except Exception as exc:
        message = str(exc)
        lowered = message.lower()
        cached = SCRAPE_CACHE.get(key)
        if cached:
            cached_copy = dict(cached)
            cached_copy["reliability_mode"] = "cache_fallback"
            cached_copy["cache_reason"] = message
            return {"ok": True, "data": cached_copy}

        fallback = {"job_description": "", "candidate_context": "", "job_source": "", "linkedin_source": ""}
        fallback_reason = ""
        try:
            if payload.job_url.strip():
                fallback["job_description"] = _direct_fetch_text(payload.job_url)
                fallback["job_source"] = "direct_fetch_fallback"
        except Exception as direct_exc:
            fallback_reason = str(direct_exc)
        if payload.linkedin_url.strip():
            fallback["candidate_context"] = (
                "LinkedIn scrape unavailable in fallback mode. "
                f"Provided URL: {payload.linkedin_url.strip()}"
            )
            fallback["linkedin_source"] = "manual_linkedin_fallback"
        if fallback["job_description"] or fallback["candidate_context"]:
            fallback["job_description_raw"] = fallback["job_description"]
            fallback["candidate_context_raw"] = fallback["candidate_context"]
            fallback["presentation_model"] = "scrape_only"
            fallback["reliability_mode"] = "direct_fetch_fallback"
            fallback["fallback_reason"] = message if not fallback_reason else f"{message}; {fallback_reason}"
            if key:
                SCRAPE_CACHE[key] = dict(fallback)
            return {"ok": True, "data": fallback}

        if (
            "credentials not found" in lowered
            or "no credentials available" in lowered
            or "authentication first" in lowered
        ):
            raise HTTPException(
                status_code=400,
                detail="Gumloop source authentication is missing for Firecrawl/Apollo. Authenticate those sources in Gumloop and retry.",
            ) from exc
        raise HTTPException(status_code=400, detail=f"Onboarding scrape failed: {message}") from exc


@app.post("/api/interview/start")
def start_interview(payload: StartInterviewRequest) -> dict:
    provider, api_key = _resolve_interview_provider()
    agent = InterviewAgent(
        job_description=payload.job_description,
        experience_level=payload.experience_level,
        interview_domain=payload.interview_domain,
        api_key=api_key,
        provider=provider,
        candidate_context=payload.candidate_context,
    )
    try:
        agent.initialize()
        slack_context = build_company_context_pack(
            interview_domain=payload.interview_domain,
            job_description=payload.job_description,
            candidate_context=payload.candidate_context,
        )
        first_question = agent.generate_question(extra_context=slack_context.get("summary", ""))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Interview init failed: {exc}") from exc

    session_id = str(uuid4())
    SESSIONS[session_id] = agent
    SESSION_META[session_id] = {"context_signals": slack_context}
    return {
        "ok": True,
        "session": _serialize_session(agent, session_id),
        "first_question": first_question,
    }


@app.post("/api/interview/demo-replay")
def demo_replay() -> dict:
    provider, api_key = _resolve_interview_provider()
    agent = InterviewAgent(
        job_description=DEMO_JOB_DESCRIPTION,
        experience_level="3-5 Years",
        interview_domain="consulting",
        api_key=api_key,
        provider=provider,
        candidate_context=DEMO_CANDIDATE_CONTEXT,
    )
    try:
        agent.initialize()
        slack_context = build_company_context_pack(
            interview_domain="consulting",
            job_description=DEMO_JOB_DESCRIPTION,
            candidate_context=DEMO_CANDIDATE_CONTEXT,
        )
        first_question = agent.generate_question(extra_context=slack_context.get("summary", ""))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Demo replay init failed: {exc}") from exc

    session_id = str(uuid4())
    SESSIONS[session_id] = agent
    SESSION_META[session_id] = {"context_signals": slack_context}
    return {
        "ok": True,
        "mode": "demo_replay",
        "session": _serialize_session(agent, session_id),
        "first_question": first_question,
        "seed": {"job_description": DEMO_JOB_DESCRIPTION, "candidate_context": DEMO_CANDIDATE_CONTEXT},
    }


@app.post("/api/interview/respond")
def respond_interview(payload: RespondRequest) -> dict:
    agent = SESSIONS.get(payload.session_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    enrichment = {"used": False, "summary": "", "source": "none", "error": "not_attempted"}
    try:
        prior_responses = [str(turn.get("response", "")) for turn in agent.session_data if isinstance(turn, dict)]
        fraud_analysis = analyze_response_integrity(
            response_text=payload.response,
            telemetry=payload.telemetry if isinstance(payload.telemetry, dict) else {},
            prior_responses=prior_responses,
        )
        gumloop_token = _resolve_gumloop_token()
        target_name = (
            agent.graph.concepts[agent.last_target_concept].name
            if agent.last_target_concept and agent.last_target_concept in agent.graph.concepts
            else "general interview signal"
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            enrichment_future = executor.submit(
                _fetch_parallel_context,
                gumloop_token,
                agent.interview_domain,
                agent.role_title,
                target_name,
                payload.response,
            )
            extraction = agent.process_response(payload.response)
            try:
                enrichment = enrichment_future.result(timeout=2.2)
            except Exception as enrich_exc:
                enrichment = {
                    "used": False,
                    "summary": "",
                    "source": "timeout",
                    "error": str(enrich_exc),
                }

        enrichment_summary = enrichment.get("summary", "") if isinstance(enrichment, dict) else ""
        next_reasoning_hint = ""
        if enrichment.get("used") and enrichment_summary:
            next_reasoning_hint = (
                "External context was fetched in parallel. Use it only if it strengthens probing depth.\n"
                f"{enrichment_summary[:900]}"
            )
        session_meta = SESSION_META.get(payload.session_id, {})
        context_signals = session_meta.get("context_signals", {}) if isinstance(session_meta, dict) else {}
        extraction["parallel_context"] = {
            "used": bool(enrichment.get("used")),
            "source": enrichment.get("source", "none"),
            "error": enrichment.get("error", ""),
        }
        extraction["fraud_analysis"] = fraud_analysis
        extraction["context_signals"] = context_signals

        for item in extraction.get("concepts_assessed", []):
            if not isinstance(item, dict):
                continue
            depth = item.get("depth_score", 0)
            evidence = str(item.get("evidence", ""))
            confidence_score, confidence_band = _concept_confidence_band(
                int(depth) if isinstance(depth, (int, float)) else 0, evidence
            )
            fraud_penalty = 1 - (0.45 * float(fraud_analysis.get("risk_score", 0.0)))
            fraud_penalty = max(0.45, min(1.0, fraud_penalty))
            adjusted_confidence = round(confidence_score * fraud_penalty, 2)
            item["confidence_score"] = round(confidence_score, 2)
            item["integrity_adjusted_confidence"] = adjusted_confidence
            item["confidence_band"] = confidence_band
        if agent.session_data:
            agent.session_data[-1]["fraud_analysis"] = fraud_analysis
            agent.session_data[-1]["input_telemetry"] = payload.telemetry

        next_question = None
        if not agent.session_complete:
            next_question = agent.generate_question(extra_context=next_reasoning_hint)
            next_question["reasoning_trace"] = {
                "gap_suggestion": suggest_next_gap(agent.graph, agent.last_target_concept),
                "parallel_context_used": bool(enrichment.get("used")),
                "parallel_context_source": enrichment.get("source", "none"),
                "fraud_risk_level": fraud_analysis.get("risk_level"),
                "fraud_risk_score": fraud_analysis.get("risk_score"),
                "company_context_used": bool(context_signals.get("used")),
                "company_context_source": context_signals.get("source", "none"),
                "company_context_mode": context_signals.get("mode", "none"),
            }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Interview step failed: {exc}") from exc

    return {
        "ok": True,
        "session": _serialize_session(agent, payload.session_id),
        "extraction": extraction,
        "next_question": next_question,
    }


@app.get("/api/interview/{session_id}/state")
def interview_state(session_id: str) -> dict:
    agent = SESSIONS.get(session_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"ok": True, "session": _serialize_session(agent, session_id)}


@app.get("/api/interview/{session_id}/report")
def interview_report(session_id: str) -> dict:
    agent = SESSIONS.get(session_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    if not agent.session_complete:
        raise HTTPException(status_code=400, detail="Session not complete yet.")

    report = generate_report(agent)
    integrity = _compute_integrity_metrics(agent)
    context_signals = SESSION_META.get(session_id, {}).get("context_signals", {})
    report_data = report.get("json", {}) if isinstance(report.get("json", {}), dict) else {}
    if report_data:
        report_data["integrity_signals"] = integrity
        report_data["context_signals"] = context_signals
    report_content = report.get("content", "")
    integrity_markdown = (
        "\n\n## Integrity Signals\n"
        f"- Average risk score: {integrity['average_risk_score']}\n"
        f"- Max risk score: {integrity['max_risk_score']}\n"
        f"- High-risk turns: {integrity['high_risk_turns']}\n"
        f"- Top flags: {', '.join(integrity['top_flags']) if integrity['top_flags'] else 'none'}\n"
        f"- Verdict: {integrity['verdict']}\n"
    )
    if "## Integrity Signals" not in report_content:
        report_content = f"{report_content}{integrity_markdown}"
    return {
        "ok": True,
        "report": report_content,
        "report_data": report_data,
        "report_source": report.get("source", "unknown"),
        "report_meta": report.get("meta", ""),
    }
