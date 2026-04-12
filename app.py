import os
import base64
import hashlib
import secrets
from urllib.parse import urlencode

import pandas as pd
import requests
import streamlit as st

from agent.interviewer import InterviewAgent
from agent.onboarding_scraper import scrape_onboarding_data
from graph.visualizer import display_graph_in_streamlit, render_legend
from report.generator import generate_report

st.set_page_config(page_title="MindMap Interviewer", page_icon="🧠", layout="wide")

GUMLOOP_AUTH_BASE = "https://api.gumloop.com"
GUMLOOP_REDIRECT_URI = "http://localhost:8501"


def inject_styles() -> None:
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;700&family=Manrope:wght@400;500;700;800&display=swap');

            :root {
                --bg: #080b12;
                --panel: rgba(14, 20, 32, 0.82);
                --panel-soft: rgba(20, 28, 43, 0.6);
                --stroke: rgba(130, 156, 255, 0.24);
                --text: #d7e0ff;
                --muted: #8ea0d1;
                --accent: #6fe0ff;
                --accent-2: #8b6dff;
                --success: #22d3a6;
            }

            .stApp {
                background:
                    radial-gradient(1200px 700px at 10% 0%, rgba(111, 224, 255, 0.14), transparent 70%),
                    radial-gradient(1000px 600px at 95% 5%, rgba(139, 109, 255, 0.16), transparent 70%),
                    linear-gradient(180deg, #05070d 0%, #090d17 100%);
                color: var(--text);
                font-family: "Manrope", sans-serif;
            }

            h1, h2, h3 {
                font-family: "Cormorant Garamond", serif !important;
                letter-spacing: 0.01em;
            }

            .hero-wrap {
                border: 1px solid var(--stroke);
                background: linear-gradient(135deg, rgba(16, 22, 35, 0.95), rgba(9, 13, 22, 0.82));
                border-radius: 20px;
                padding: 1.2rem 1.35rem 1.05rem 1.35rem;
                margin-bottom: 1rem;
                box-shadow: 0 30px 80px rgba(0, 0, 0, 0.35);
                backdrop-filter: blur(8px);
            }

            .hero-kicker {
                font-size: 0.72rem;
                letter-spacing: 0.14em;
                color: var(--accent);
                text-transform: uppercase;
                font-weight: 800;
            }

            .hero-title {
                font-size: 2.1rem;
                margin: 0.15rem 0 0.35rem 0;
                color: #f3f7ff;
                line-height: 1;
            }

            .hero-sub {
                color: var(--muted);
                font-size: 0.95rem;
                line-height: 1.5;
            }

            .chip-row {
                display: flex;
                gap: 0.5rem;
                flex-wrap: wrap;
                margin-top: 0.75rem;
            }

            .chip {
                border: 1px solid rgba(111, 224, 255, 0.35);
                background: rgba(25, 34, 53, 0.65);
                color: #c7f2ff;
                border-radius: 999px;
                padding: 0.24rem 0.64rem;
                font-size: 0.72rem;
                font-weight: 700;
            }

            .surface-card {
                border: 1px solid var(--stroke);
                background: var(--panel);
                border-radius: 16px;
                padding: 0.9rem 1rem 0.7rem 1rem;
                margin-bottom: 0.85rem;
                box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 18px 32px rgba(0,0,0,0.3);
            }

            .surface-title {
                font-size: 0.75rem;
                letter-spacing: 0.11em;
                text-transform: uppercase;
                font-weight: 800;
                color: #9bb3f2;
                margin-bottom: 0.25rem;
            }

            .surface-body {
                font-size: 0.9rem;
                color: var(--text);
            }

            .status-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 0.55rem;
                margin-top: 0.45rem;
            }

            .status-pill {
                border-radius: 12px;
                padding: 0.56rem 0.58rem;
                background: var(--panel-soft);
                border: 1px solid rgba(130, 156, 255, 0.2);
            }

            .status-label {
                color: var(--muted);
                font-size: 0.67rem;
                text-transform: uppercase;
                letter-spacing: 0.08em;
                font-weight: 700;
            }

            .status-value {
                color: #f4f8ff;
                font-size: 1.03rem;
                font-weight: 800;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st.markdown(
        """
        <div class="hero-wrap">
          <div class="hero-kicker">Adaptive Interview Intelligence</div>
          <div class="hero-title">MindMap Interviewer</div>
          <div class="hero-sub">
            Build a live knowledge graph while interviewing. Every answer updates concept depth,
            reveals blind spots, and drives the next probing question.
          </div>
          <div class="chip-row">
            <span class="chip">Live Concept Graph</span>
            <span class="chip">Gap-Targeted Questions</span>
            <span class="chip">Evidence-Based Evaluation</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def init_session_state() -> None:
    defaults = {
        "agent": None,
        "messages": [],
        "initialized": False,
        "session_active": False,
        "report_markdown": None,
        "job_description_seed": "",
        "candidate_context": "",
        "linkedin_url": "",
        "job_url": "",
        "onboarding_note": "",
        "gumloop_client_id": "",
        "gumloop_access_token": "",
        "gumloop_auth_state": "",
        "gumloop_code_verifier": "",
        "gumloop_auth_url": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_interview_state() -> None:
    st.session_state.agent = None
    st.session_state.messages = []
    st.session_state.initialized = False
    st.session_state.session_active = False
    st.session_state.report_markdown = None
    st.session_state.job_description_seed = ""
    st.session_state.candidate_context = ""
    st.session_state.linkedin_url = ""
    st.session_state.job_url = ""
    st.session_state.onboarding_note = ""
    st.session_state.gumloop_client_id = ""
    st.session_state.gumloop_access_token = ""
    st.session_state.gumloop_auth_state = ""
    st.session_state.gumloop_code_verifier = ""
    st.session_state.gumloop_auth_url = ""


def _pkce_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def ensure_gumloop_client_id() -> str:
    if st.session_state.gumloop_client_id:
        return st.session_state.gumloop_client_id
    payload = {
        "client_name": "MindMap Interviewer",
        "redirect_uris": [GUMLOOP_REDIRECT_URI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    response = requests.post(
        f"{GUMLOOP_AUTH_BASE}/oauth/register", json=payload, timeout=20
    )
    response.raise_for_status()
    client_id = response.json().get("client_id", "")
    if not client_id:
        raise ValueError("Gumloop OAuth registration returned no client_id.")
    st.session_state.gumloop_client_id = client_id
    return client_id


def start_gumloop_auth() -> str:
    client_id = ensure_gumloop_client_id()
    state = secrets.token_urlsafe(20)
    verifier = secrets.token_urlsafe(64)
    challenge = _pkce_code_challenge(verifier)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": GUMLOOP_REDIRECT_URI,
        "scope": "gumstack",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{GUMLOOP_AUTH_BASE}/oauth/authorize?{urlencode(params)}"
    st.session_state.gumloop_auth_state = state
    st.session_state.gumloop_code_verifier = verifier
    st.session_state.gumloop_auth_url = auth_url
    return auth_url


def maybe_finish_gumloop_auth() -> None:
    params = st.query_params
    code = params.get("code")
    state = params.get("state")
    if not code or not state:
        return

    if state != st.session_state.gumloop_auth_state:
        st.session_state.onboarding_note = "Gumloop auth failed: state mismatch."
        params.clear()
        return

    token_payload = {
        "grant_type": "authorization_code",
        "client_id": st.session_state.gumloop_client_id,
        "code": code,
        "redirect_uri": GUMLOOP_REDIRECT_URI,
        "code_verifier": st.session_state.gumloop_code_verifier,
    }
    response = requests.post(
        f"{GUMLOOP_AUTH_BASE}/oauth/token", data=token_payload, timeout=20
    )
    if response.status_code >= 400:
        st.session_state.onboarding_note = f"Gumloop auth failed: {response.text}"
        params.clear()
        return

    body = response.json()
    access_token = body.get("access_token", "")
    if not access_token:
        st.session_state.onboarding_note = "Gumloop auth failed: no access token."
        params.clear()
        return

    st.session_state.gumloop_access_token = access_token
    os.environ["GUMLOOP_MCP_TOKEN"] = access_token
    st.session_state.onboarding_note = "Gumloop connected successfully."
    params.clear()


def start_interview(
    job_description: str, experience_level: str, candidate_context: str
) -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        st.error("Server is missing ANTHROPIC_API_KEY.")
        return
    if not job_description.strip():
        st.error("Please provide a job description.")
        return

    agent = InterviewAgent(
        job_description=job_description,
        experience_level=experience_level,
        api_key=api_key,
        provider="anthropic",
        candidate_context=candidate_context,
    )
    try:
        with st.spinner("Analyzing job description and building concept map..."):
            agent.initialize()
    except Exception as exc:
        st.error(f"Unable to initialize interview: {exc}")
        return

    st.session_state.agent = agent
    st.session_state.messages = []
    st.session_state.initialized = True
    st.session_state.session_active = True
    st.session_state.report_markdown = None

    try:
        first_q = agent.generate_question()
    except Exception as exc:
        st.error(f"Unable to generate first question: {exc}")
        st.session_state.session_active = False
        return

    st.session_state.messages.append(
        {"role": "assistant", "content": first_q["message"], "meta": first_q}
    )
    st.rerun()


def render_sidebar() -> tuple[str, str, str, bool, bool]:
    with st.sidebar:
        st.markdown("### Control Deck")
        st.caption("Anthropic mode is enabled with background API key.")
        st.markdown("#### Onboarding Sources")
        auth_col, disconnect_col = st.columns(2)
        with auth_col:
            connect_btn = st.button("Connect Gumloop", use_container_width=True)
        with disconnect_col:
            disconnect_btn = st.button("Disconnect", use_container_width=True)

        if connect_btn:
            try:
                auth_url = start_gumloop_auth()
                st.link_button("Open Gumloop Login", auth_url, use_container_width=True)
                st.caption("Complete login, then come back to this tab.")
            except Exception as exc:
                st.session_state.onboarding_note = f"Gumloop auth start failed: {exc}"
        if disconnect_btn:
            st.session_state.gumloop_access_token = ""
            os.environ.pop("GUMLOOP_MCP_TOKEN", None)
            st.session_state.onboarding_note = "Gumloop token cleared."

        if st.session_state.gumloop_access_token:
            st.caption("Gumloop status: Connected")
        else:
            st.caption("Gumloop status: Not connected")

        linkedin_url = st.text_input(
            "Candidate LinkedIn URL",
            value=st.session_state.linkedin_url,
            placeholder="https://www.linkedin.com/in/...",
        )
        job_url = st.text_input(
            "Job Posting URL",
            value=st.session_state.job_url,
            placeholder="https://company.com/jobs/...",
        )
        fetch_btn = st.button("Fetch from URLs (Apollo + Firecrawl)", use_container_width=True)
        if fetch_btn:
            st.session_state.linkedin_url = linkedin_url.strip()
            st.session_state.job_url = job_url.strip()
            try:
                with st.spinner("Scraping onboarding data from Gumloop MCP..."):
                    scraped = scrape_onboarding_data(
                        linkedin_url=linkedin_url.strip(),
                        job_url=job_url.strip(),
                        gumloop_token=st.session_state.gumloop_access_token,
                    )
                if scraped.get("job_description"):
                    st.session_state.job_description_seed = scraped["job_description"]
                if scraped.get("candidate_context"):
                    st.session_state.candidate_context = scraped["candidate_context"]

                source_bits = []
                if scraped.get("linkedin_source"):
                    source_bits.append(f"Apollo:{scraped['linkedin_source']}")
                if scraped.get("job_source"):
                    source_bits.append(f"Firecrawl:{scraped['job_source']}")
                st.session_state.onboarding_note = (
                    "Scrape complete."
                    if not source_bits
                    else f"Scrape complete ({', '.join(source_bits)})."
                )
            except Exception as exc:
                st.session_state.onboarding_note = (
                    f"Auto-fetch failed: {exc}. Set GUMLOOP_MCP_TOKEN and verify MCP tool access."
                )

        if st.session_state.onboarding_note:
            st.caption(st.session_state.onboarding_note)

        job_description = st.text_area(
            "Job Description",
            value=st.session_state.job_description_seed,
            height=220,
            placeholder="Paste JD manually or fetch from Job URL.",
        )
        candidate_context = st.text_area(
            "Candidate Context (from LinkedIn)",
            value=st.session_state.candidate_context,
            height=130,
            placeholder="Auto-filled from LinkedIn URL if Apollo scrape succeeds.",
        )
        experience_level = st.select_slider(
            "Experience Level",
            options=["Fresher", "1-2 Years", "3-5 Years", "Senior (5+)"],
        )
        can_start = bool(job_description.strip())
        start_btn = st.button("Start Interview", type="primary", use_container_width=True)
        reset_btn = st.button("Reset Session", use_container_width=True)
        if not can_start:
            st.caption("Add JD to enable a full run.")

        agent = st.session_state.agent
        session_status = (
            "Active"
            if st.session_state.session_active
            else "Ready"
            if st.session_state.initialized
            else "Idle"
        )
        st.markdown(
            f"""
            <div class="surface-card">
              <div class="surface-title">Session Status</div>
              <div class="surface-body">{session_status}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if agent:
            st.divider()
            stats = agent.graph.get_stats()
            st.metric("Concepts Explored", f"{stats['explored']}/{stats['total']}")
            st.metric("Deep Understanding", f"{stats['deep_pct']}%")
            st.metric("Avg Depth", f"{stats['avg_depth']}/3")
            st.divider()
            render_legend()

    return job_description, experience_level, candidate_context, start_btn, reset_btn


def render_chat_column() -> None:
    st.subheader("Interview")
    agent = st.session_state.agent

    if agent:
        asked = len(agent.session_data)
        progress = min(asked / 8, 1.0)
        st.progress(progress, text=f"Interview Progress: {asked}/8 answered")
    elif not st.session_state.initialized:
        st.info("Start an interview from the sidebar to begin the chat.")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg["role"] == "assistant" and "meta" in msg and agent:
                target = msg["meta"].get("target_concept_id")
                concept = agent.graph.concepts.get(target) if target else None
                if concept is not None:
                    st.caption(f"🎯 _Targeting: {concept.name}_")

    if st.session_state.session_active and agent:
        user_input = st.chat_input("Your answer...")
        if not user_input:
            return

        st.session_state.messages.append({"role": "user", "content": user_input})
        try:
            with st.spinner("Analyzing your response..."):
                extraction = agent.process_response(user_input)
        except Exception as exc:
            st.error(f"Failed to process response: {exc}")
            return

        if agent.session_complete:
            st.session_state.session_active = False
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": "Great session! Your concept map is complete. Check the report below.",
                    "meta": {},
                }
            )
            st.rerun()
            return

        try:
            next_q = agent.generate_question()
        except Exception as exc:
            st.error(f"Failed to generate next question: {exc}")
            st.session_state.session_active = False
            return

        quality = extraction.get("overall_response_quality", "")
        prefix = ""
        if quality == "shallow":
            prefix = "I'd like to dig a bit deeper on that. "
        elif quality == "strong" and extraction.get("notable_insight"):
            prefix = f"Interesting point about {extraction['notable_insight']}. "

        st.session_state.messages.append(
            {"role": "assistant", "content": prefix + next_q["message"], "meta": next_q}
        )
        st.rerun()


def render_graph_column() -> None:
    st.subheader("Live Knowledge Map")
    agent = st.session_state.agent

    if agent and st.session_state.initialized:
        stats = agent.graph.get_stats()
        st.markdown(
            f"""
            <div class="surface-card">
              <div class="surface-title">Coverage Snapshot</div>
              <div class="status-grid">
                <div class="status-pill">
                  <div class="status-label">Explored</div>
                  <div class="status-value">{stats['explored']}/{stats['total']}</div>
                </div>
                <div class="status-pill">
                  <div class="status-label">Deep</div>
                  <div class="status-value">{stats['deep_pct']}%</div>
                </div>
                <div class="status-pill">
                  <div class="status-label">Avg Depth</div>
                  <div class="status-value">{stats['avg_depth']}/3</div>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        display_graph_in_streamlit(
            agent.graph, height=450, highlight_concept_id=agent.last_target_concept
        )
        st.subheader("Concept Scores")
        rows = []
        depth_labels = {0: "⬜ Unexplored", 1: "🟥 Surface", 2: "🟨 Partial", 3: "🟩 Deep"}
        importance_order = {"critical": 0, "important": 1, "nice_to_have": 2}
        for concept in agent.graph.concepts.values():
            rows.append(
                {
                    "Concept": concept.name,
                    "Category": concept.category.title(),
                    "Importance": concept.importance.replace("_", " ").title(),
                    "Depth": depth_labels[concept.depth_score],
                    "Score": f"{concept.depth_score}/3",
                    "_depth_sort": concept.depth_score,
                    "_importance_sort": importance_order.get(concept.importance, 3),
                }
            )
        df = (
            pd.DataFrame(rows)
            .sort_values(by=["_depth_sort", "_importance_sort", "Concept"])
            .drop(columns=["_depth_sort", "_importance_sort"])
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info(
            "Paste a job description and start the interview to see the concept map build in real time."
        )


def render_report_section() -> None:
    agent = st.session_state.agent
    if not agent or st.session_state.session_active or not st.session_state.initialized:
        return

    st.divider()
    st.header("📊 Interview Evaluation Report")

    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("Final Knowledge Map")
        display_graph_in_streamlit(agent.graph, height=400)
    with col2:
        stats = agent.graph.get_stats()
        st.subheader("Coverage Summary")
        st.metric("Total Concepts", stats["total"])
        st.metric("Explored", f"{stats['explored']} ({stats['coverage_pct']}%)")
        st.metric("Deep Understanding", f"{stats['deep']} ({stats['deep_pct']}%)")
        st.metric("Average Depth", f"{stats['avg_depth']}/3")

    if st.session_state.report_markdown is None:
        try:
            with st.spinner("Generating detailed report..."):
                st.session_state.report_markdown = generate_report(agent)
        except Exception as exc:
            st.session_state.report_markdown = f"Report generation failed: {exc}"

    st.markdown(st.session_state.report_markdown)


def main() -> None:
    inject_styles()
    init_session_state()
    maybe_finish_gumloop_auth()
    render_header()
    (
        job_description,
        experience_level,
        candidate_context,
        start_btn,
        reset_btn,
    ) = render_sidebar()
    if reset_btn:
        reset_interview_state()
        st.rerun()
    if start_btn:
        start_interview(job_description, experience_level, candidate_context)

    if not st.session_state.initialized:
        st.markdown(
            """
            <div class="surface-card">
              <div class="surface-title">How To Demo</div>
              <div class="surface-body">
                1) Paste JD and choose level in the sidebar.<br>
                2) Start the interview and answer naturally.<br>
                3) Watch nodes shift from unexplored to deep as evidence accumulates.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    col_chat, col_graph = st.columns([1, 1])
    with col_chat:
        render_chat_column()
    with col_graph:
        render_graph_column()

    render_report_section()


if __name__ == "__main__":
    main()
