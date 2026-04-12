import { useState } from "react";

import { api } from "./api";
import ConceptGraph from "./components/ConceptGraph";

const LEVELS = ["Fresher", "1-2 Years", "3-5 Years", "Senior (5+)"];
const DOMAINS = [
  {
    id: "software_engineering",
    title: "Software Engineering",
    hint: "Systems design, implementation detail, debugging trade-offs",
  },
  {
    id: "consulting",
    title: "Consulting",
    hint: "Hypothesis-driven reasoning, structured decomposition, business judgment",
  },
];

function createTypingTelemetry() {
  return {
    startedAt: 0,
    firstKeyAt: 0,
    lastKeyAt: 0,
    keyCount: 0,
    backspaceCount: 0,
    pasteCount: 0,
    pastedChars: 0,
    intervals: [],
  };
}

export default function App() {
  const [linkedinUrl, setLinkedinUrl] = useState("");
  const [jobUrl, setJobUrl] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [candidateContext, setCandidateContext] = useState("");
  const [experienceLevel, setExperienceLevel] = useState(LEVELS[1]);
  const [sessionId, setSessionId] = useState("");
  const [session, setSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [report, setReport] = useState("");
  const [reportData, setReportData] = useState(null);
  const [reportSource, setReportSource] = useState("");
  const [activityEvents, setActivityEvents] = useState([]);
  const [lastTurnAnalysis, setLastTurnAnalysis] = useState(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [noteType, setNoteType] = useState("info");
  const [actionLabel, setActionLabel] = useState("");
  const [onboardingStep, setOnboardingStep] = useState(1);
  const [interviewDomain, setInterviewDomain] = useState(DOMAINS[0].id);
  const [currentView, setCurrentView] = useState("onboarding");
  const [typingTelemetry, setTypingTelemetry] = useState(createTypingTelemetry());
  const [lastAssistantAt, setLastAssistantAt] = useState(Date.now());

  const sessionComplete = Boolean(session?.session_complete);

  async function primeInterview(jobText, candidateText, successNote) {
    const response = await api.startInterview({
      job_description: jobText,
      experience_level: experienceLevel,
      interview_domain: interviewDomain,
      candidate_context: candidateText,
    });
    setSessionId(response.session.session_id);
    setSession(response.session);
    setReport("");
    setReportData(null);
    setReportSource("");
    setLastTurnAnalysis(null);
    setMessages([
      {
        role: "assistant",
        content: response.first_question.message,
        meta: {
          targetConceptId: response.first_question.target_concept_id,
          reasoning: response.first_question.reasoning,
          evidenceAnchor: response.first_question.evidence_anchor,
          trace: response.first_question.reasoning_trace,
        },
      },
    ]);
    setLastAssistantAt(Date.now());
    setNote(successNote);
    setNoteType("success");
  }

  function friendlyError(error) {
    const message = String(error?.message || error || "");
    if (
      message.toLowerCase().includes("credentials not found") ||
      message.toLowerCase().includes("no credentials available") ||
      message.toLowerCase().includes("authentication first")
    ) {
      return "Gumloop source auth is incomplete for Firecrawl/Apollo. Connect credentials in Gumloop and retry.";
    }
    return message;
  }

  async function fetchOnboarding() {
    setBusy(true);
    setActionLabel("Fetching scrape data...");
    setNote("");
    setNoteType("info");
    try {
      const response = await api.scrape({
        linkedin_url: linkedinUrl,
        job_url: jobUrl,
      });
      const data = response.data || {};
      const scrapedJob = data.job_description || "";
      const scrapedCandidate = data.candidate_context || "";
      if (scrapedJob) setJobDescription(scrapedJob);
      if (scrapedCandidate) setCandidateContext(scrapedCandidate);
      const reliabilityMode = data.reliability_mode || "live";
      if (reliabilityMode === "cache_fallback") {
        setNote("Live scrape failed, but recovered from cached data. Review in Step 2 and continue.");
      } else if (reliabilityMode === "direct_fetch_fallback") {
        setNote("Live scrape degraded to direct fetch fallback. Review content in Step 2 before interview.");
      } else {
        setNote("Fetched successfully. Review/edit in Step 2, then click Begin Interview.");
      }
      setNoteType("success");
      setOnboardingStep(2);
    } catch (error) {
      setNote(friendlyError(error));
      setNoteType("error");
      setOnboardingStep(1);
    } finally {
      setBusy(false);
      setActionLabel("");
    }
  }

  async function startInterview() {
    if (!jobDescription.trim()) {
      setNote("Job description is required.");
      setNoteType("error");
      return;
    }
    setBusy(true);
    setActionLabel("Applying edits and regenerating first question...");
    setNote("");
    try {
      await primeInterview(
        jobDescription,
        candidateContext,
        "Interview started. First question is ready."
      );
      setCurrentView("interview");
    } catch (error) {
      setNote(friendlyError(error));
      setNoteType("error");
    } finally {
      setBusy(false);
      setActionLabel("");
    }
  }

  async function startDemoReplay() {
    setBusy(true);
    setActionLabel("Loading reliability demo seed...");
    setNote("");
    try {
      const response = await api.demoReplay();
      const seed = response.seed || {};
      if (seed.job_description) setJobDescription(seed.job_description);
      if (seed.candidate_context) setCandidateContext(seed.candidate_context);
      setSessionId(response.session.session_id);
      setSession(response.session);
      setReport("");
      setReportData(null);
      setReportSource("");
      setLastTurnAnalysis(null);
      setMessages([
        {
          role: "assistant",
          content: response.first_question.message,
          meta: {
            targetConceptId: response.first_question.target_concept_id,
            reasoning: response.first_question.reasoning,
            evidenceAnchor: response.first_question.evidence_anchor,
            trace: response.first_question.reasoning_trace,
          },
        },
      ]);
      setLastAssistantAt(Date.now());
      setNote("Demo replay session started. This is your zero-fail fallback path.");
      setNoteType("success");
      setCurrentView("interview");
    } catch (error) {
      setNote(friendlyError(error));
      setNoteType("error");
    } finally {
      setBusy(false);
      setActionLabel("");
    }
  }

  async function sendResponse() {
    if (!sessionId || !input.trim()) return;
    const userMessage = input.trim();
    const now = Date.now();
    const intervals = typingTelemetry.intervals || [];
    const avgInterKeyMs =
      intervals.length > 0 ? intervals.reduce((sum, value) => sum + value, 0) / intervals.length : 0;
    const telemetryPayload = {
      char_count: userMessage.length,
      key_count: typingTelemetry.keyCount,
      backspace_count: typingTelemetry.backspaceCount,
      paste_count: typingTelemetry.pasteCount,
      pasted_chars: typingTelemetry.pastedChars,
      typing_duration_ms:
        typingTelemetry.firstKeyAt && typingTelemetry.lastKeyAt
          ? Math.max(0, typingTelemetry.lastKeyAt - typingTelemetry.firstKeyAt)
          : 0,
      response_latency_ms: Math.max(0, now - lastAssistantAt),
      avg_inter_key_ms: Number.isFinite(avgInterKeyMs) ? Math.round(avgInterKeyMs) : 0,
    };
    setInput("");
    setTypingTelemetry(createTypingTelemetry());
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setBusy(true);
    setActionLabel("Analyzing answer and preparing next question...");
    try {
      const response = await api.respondInterview({
        session_id: sessionId,
        response: userMessage,
        telemetry: telemetryPayload,
      });
      setSession(response.session);
      setLastTurnAnalysis(response.extraction || null);
      if (response.next_question?.message) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: response.next_question.message,
            meta: {
              targetConceptId: response.next_question.target_concept_id,
              reasoning: response.next_question.reasoning,
              evidenceAnchor: response.next_question.evidence_anchor,
              trace: response.next_question.reasoning_trace,
            },
          },
        ]);
        setLastAssistantAt(Date.now());
      } else if (response.session?.session_complete) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: "Interview complete. Generate report below." },
        ]);
        setLastAssistantAt(Date.now());
      }
    } catch (error) {
      setNote(friendlyError(error));
      setNoteType("error");
    } finally {
      setBusy(false);
      setActionLabel("");
    }
  }

  async function fetchReport() {
    if (!sessionId) return;
    setBusy(true);
    setActionLabel("Generating final evaluation report...");
    try {
      const response = await api.getReport(sessionId);
      setReport(response.report || "");
      setReportData(response.report_data || null);
      setReportSource(response.report_source || "");
    } catch (error) {
      setNote(friendlyError(error));
      setNoteType("error");
    } finally {
      setBusy(false);
      setActionLabel("");
    }
  }

  async function refreshActivity() {
    try {
      const response = await api.activity(25);
      setActivityEvents(response.events || []);
    } catch (_error) {
      // keep silent to avoid interrupting interview flow
    }
  }

  function resetAll() {
    setSessionId("");
    setSession(null);
    setMessages([]);
    setInput("");
    setReport("");
    setReportData(null);
    setReportSource("");
    setNote("");
    setNoteType("info");
    setActionLabel("");
    setOnboardingStep(1);
    setCurrentView("onboarding");
    setTypingTelemetry(createTypingTelemetry());
    setLastAssistantAt(Date.now());
  }

  return (
    <div className="app-shell mx-auto min-h-screen px-4 py-8 md:px-8">
      <header className="glass-panel dot-grid mb-6 rounded-3xl p-7">
        <p className="luxury-kicker text-xs">
          Gumloop Native Interview OS
        </p>
        <h1 className="brand-title mt-2 text-4xl font-bold text-slate-900">MindMap Interviewer</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Designed for evaluator-grade interviews: context-aware questioning, live concept depth,
          and evidence-backed decisions rendered in a Gumloop-style control surface.
        </p>
        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            className="btn-tertiary gumloop-button-shadow rounded-lg px-3 py-1 text-xs font-semibold"
            onClick={refreshActivity}
          >
            Refresh Localhost Activity
          </button>
          <span className="stat-chip rounded-full px-2 py-1 text-xs">
            {activityEvents.length > 0 ? `${activityEvents.length} recent backend events` : "No events yet"}
          </span>
        </div>
      </header>

      {currentView === "onboarding" ? (
        <div className="mx-auto max-w-2xl">
          <aside className="glass-panel rounded-2xl p-4">
          <h2 className="text-lg font-semibold text-slate-900">Onboarding</h2>
          <p className="mt-1 text-xs text-slate-500">
            1) add sources 2) review scraped content 3) begin interview.
          </p>
          <div className="mt-3 grid grid-cols-2 gap-1 rounded-xl bg-[var(--surface-muted)] p-1 text-[11px] font-semibold">
            {[1, 2].map((step) => (
              <button
                key={step}
                className={`rounded-lg px-2 py-1 ${
                  onboardingStep === step
                    ? "bg-white text-slate-900 shadow-sm"
                    : "text-slate-500 hover:text-slate-700"
                }`}
                onClick={() => setOnboardingStep(step)}
                type="button"
              >
                Step {step}
              </button>
            ))}
          </div>
          <div className="mt-3 space-y-3">
            {busy && actionLabel ? (
              <div className="flex items-center gap-2 rounded-xl border border-pink-400/35 bg-white p-2 text-xs text-slate-600">
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-pink-400" />
                {actionLabel}
              </div>
            ) : null}
            {onboardingStep === 1 ? (
              <>
                <label className="text-xs font-semibold text-slate-500">
                  Step 1 - Source URLs and Fetch
                </label>
                <input
                  className="app-input w-full rounded-xl px-3 py-2 text-sm"
                  placeholder="LinkedIn URL"
                  value={linkedinUrl}
                  onChange={(event) => setLinkedinUrl(event.target.value)}
                />
                <input
                  className="app-input w-full rounded-xl px-3 py-2 text-sm"
                  placeholder="Job URL"
                  value={jobUrl}
                  onChange={(event) => setJobUrl(event.target.value)}
                />
                <div className="space-y-2">
                  {DOMAINS.map((domain) => (
                    <button
                      key={domain.id}
                      type="button"
                      onClick={() => setInterviewDomain(domain.id)}
                  className={`w-full rounded-xl border px-3 py-2 text-left ${
                        interviewDomain === domain.id
                          ? "border-pink-300/70 bg-pink-500/10"
                          : "border-[var(--border)] bg-white"
                      }`}
                    >
                      <div className="text-sm font-semibold text-slate-800">{domain.title}</div>
                      <div className="text-xs text-slate-500">{domain.hint}</div>
                    </button>
                  ))}
                </div>
                <select
                  className="app-input w-full rounded-xl px-3 py-2 text-sm"
                  value={experienceLevel}
                  onChange={(event) => setExperienceLevel(event.target.value)}
                >
                  {LEVELS.map((level) => (
                    <option value={level} key={level}>
                      {level}
                    </option>
                  ))}
                </select>
                <button
                  onClick={fetchOnboarding}
                  disabled={busy || (!linkedinUrl.trim() && !jobUrl.trim())}
                  className="btn-secondary gumloop-button-shadow w-full rounded-xl px-3 py-2 text-sm font-bold disabled:opacity-60"
                >
                  {busy ? "Fetching..." : "Fetch scraped content"}
                </button>
                <button
                  onClick={startDemoReplay}
                  disabled={busy}
                  className="btn-tertiary w-full rounded-xl px-3 py-2 text-sm font-semibold"
                >
                  {busy && actionLabel.includes("demo") ? "Loading..." : "Run Demo Replay (reliability mode)"}
                </button>
                <button
                  className="btn-tertiary w-full rounded-xl px-3 py-2 text-sm font-semibold"
                  type="button"
                  onClick={() => setOnboardingStep(2)}
                >
                  Continue to Review
                </button>
              </>
            ) : null}
            {onboardingStep === 2 ? (
              <>
                <label className="text-xs font-semibold text-slate-500">
                  Step 2 - Review/Edit Content
                </label>
                <textarea
                  className="app-input h-40 w-full rounded-xl px-3 py-2 text-sm"
                  placeholder="JD content from scrape (editable)"
                  value={jobDescription}
                  onChange={(event) => setJobDescription(event.target.value)}
                />
                <textarea
                  className="app-input h-28 w-full rounded-xl px-3 py-2 text-sm"
                  placeholder="Candidate profile details from scrape (editable)"
                  value={candidateContext}
                  onChange={(event) => setCandidateContext(event.target.value)}
                />
                <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] p-3 text-xs text-slate-600">
                  <div className="font-semibold text-slate-800">Current Setup</div>
                  <div className="mt-1">Domain: {DOMAINS.find((d) => d.id === interviewDomain)?.title}</div>
                  <div>Experience: {experienceLevel}</div>
                  <div>Candidate context chars: {candidateContext.length}</div>
                  <div>JD chars: {jobDescription.length}</div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    className="btn-tertiary w-full rounded-xl px-3 py-2 text-sm font-semibold"
                    type="button"
                    onClick={() => setOnboardingStep(1)}
                  >
                    Back
                  </button>
                  <button
                    onClick={startInterview}
                    disabled={busy || !jobDescription.trim()}
                    className="btn-primary gumloop-button-shadow w-full rounded-xl px-3 py-2 text-sm font-bold disabled:opacity-60"
                  >
                    {busy ? "Starting..." : "Begin Interview"}
                  </button>
                </div>
              </>
            ) : null}
            <button
              onClick={resetAll}
              className="btn-tertiary w-full rounded-xl px-3 py-2 text-sm font-semibold"
            >
              Reset Session
            </button>
            {note ? (
              <div
                className={`rounded-xl border p-2 text-xs ${
                  noteType === "success"
                    ? "border-emerald-500/30 score-success"
                    : noteType === "error"
                      ? "border-[var(--danger-fg)]/30 score-danger"
                      : "border-[var(--border)] score-idle"
                }`}
              >
                {note}
              </div>
            ) : null}
          </div>
          </aside>
        </div>
      ) : (
        <main className="space-y-4">
          <div className="flex items-center justify-between rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-2 text-xs text-slate-600">
            <div>
              Domain: {DOMAINS.find((d) => d.id === interviewDomain)?.title} | Experience: {experienceLevel} | Questions: {session?.question_count ?? 0}/{session?.max_questions ?? 8}
            </div>
            <button
              type="button"
              className="btn-tertiary rounded-lg px-3 py-1 text-xs font-semibold"
              onClick={() => setCurrentView("onboarding")}
            >
              Edit Onboarding
            </button>
          </div>
          {session?.context_signals?.source ? (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-2 text-xs text-slate-600">
              Context source: {session.context_signals.source} | mode: {session.context_signals.mode || "n/a"} | status: {session.context_signals.status || "n/a"}
            </div>
          ) : null}
          {note ? (
            <div
              className={`rounded-xl border p-2 text-xs ${
                noteType === "success"
                  ? "border-emerald-500/30 score-success"
                  : noteType === "error"
                    ? "border-[var(--danger-fg)]/30 score-danger"
                    : "border-[var(--border)] score-idle"
              }`}
            >
              {note}
            </div>
          ) : null}
          <div className="grid gap-4 xl:grid-cols-2">
            <section className="glass-panel rounded-2xl p-4">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-slate-900">Interview Chat</h2>
                {sessionComplete ? (
                  <button
                    onClick={fetchReport}
                    disabled={busy}
                    className="gumloop-button-shadow rounded-lg border border-emerald-600 bg-gradient-to-b from-emerald-500 to-emerald-600 px-3 py-1 text-xs font-bold text-white"
                  >
                    {busy && actionLabel.startsWith("Generating final") ? "Generating..." : "Generate Report"}
                  </button>
                ) : null}
              </div>
              <div className="h-[420px] space-y-2 overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] p-3">
                {messages.length === 0 ? (
                  <div className="text-sm text-slate-500">Start interview to begin.</div>
                ) : (
                  messages.map((msg, idx) => (
                    <div key={`${msg.role}-${idx}`}>
                      <div
                        className={`rounded-xl px-3 py-2 text-sm ${
                          msg.role === "assistant"
                            ? "assistant-bubble mr-8 text-slate-700"
                            : "user-bubble ml-8 text-slate-700"
                        }`}
                      >
                        {msg.content}
                      </div>
                      {msg.role === "assistant" && msg.meta?.reasoning ? (
                        <div className="mr-8 mt-1 rounded-md border border-[var(--border)] bg-white px-2 py-1 text-[11px] text-slate-500">
                          Why this question: {msg.meta.reasoning}
                          {msg.meta.evidenceAnchor ? ` | Anchor: ${msg.meta.evidenceAnchor}` : ""}
                          {msg.meta.trace?.parallel_context_used ? " | External context: used" : " | External context: none"}
                        </div>
                      ) : null}
                    </div>
                  ))
                )}
              </div>
              <div className="mt-3 flex gap-2">
                <input
                  className="app-input w-full rounded-xl px-3 py-2 text-sm"
                  placeholder="Your answer..."
                  value={input}
                  onChange={(event) => {
                    setInput(event.target.value);
                    setTypingTelemetry((prev) => {
                      if (prev.startedAt) return prev;
                      return { ...prev, startedAt: Date.now() };
                    });
                  }}
                  onPaste={(event) => {
                    const pasted = event.clipboardData?.getData("text") || "";
                    setTypingTelemetry((prev) => ({
                      ...prev,
                      startedAt: prev.startedAt || Date.now(),
                      pasteCount: prev.pasteCount + 1,
                      pastedChars: prev.pastedChars + pasted.length,
                    }));
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") sendResponse();
                    const now = Date.now();
                    setTypingTelemetry((prev) => {
                      const interval =
                        prev.lastKeyAt && prev.lastKeyAt > 0 ? Math.max(0, now - prev.lastKeyAt) : null;
                      const nextIntervals = interval !== null ? [...prev.intervals, interval].slice(-120) : prev.intervals;
                      return {
                        ...prev,
                        startedAt: prev.startedAt || now,
                        firstKeyAt: prev.firstKeyAt || now,
                        lastKeyAt: now,
                        keyCount: prev.keyCount + 1,
                        backspaceCount: prev.backspaceCount + (event.key === "Backspace" ? 1 : 0),
                        intervals: nextIntervals,
                      };
                    });
                  }}
                />
                <button
                  onClick={sendResponse}
                  disabled={busy || !sessionId}
                  className="btn-secondary gumloop-button-shadow rounded-xl px-4 py-2 text-sm font-bold disabled:opacity-60"
                >
                  {busy && actionLabel.startsWith("Analyzing answer") ? "..." : "Send"}
                </button>
              </div>
              {lastTurnAnalysis?.concepts_assessed?.length ? (
                <div className="report-card mt-3 rounded-xl p-3 text-xs text-slate-600">
                  <div className="mb-2 font-semibold text-slate-800">Turn Evidence + Confidence</div>
                  <div className="space-y-1">
                    {lastTurnAnalysis.concepts_assessed.slice(0, 4).map((item) => (
                      <div key={`${item.concept_id}-${item.evidence}`} className="rounded-lg bg-white px-2 py-1">
                        <span className="font-semibold">{item.concept_id}</span>: {item.evidence || "No explicit evidence"} | depth {item.depth_score} | confidence {item.confidence_band} ({item.confidence_score})
                      </div>
                    ))}
                  </div>
                  <div className="mt-2 text-[11px] text-slate-500">
                    Parallel context source: {lastTurnAnalysis.parallel_context?.source || "none"} | used: {lastTurnAnalysis.parallel_context?.used ? "yes" : "no"}
                  </div>
                  {lastTurnAnalysis.fraud_analysis ? (
                    <div className="mt-2 rounded-md border border-[var(--border)] bg-white px-2 py-1 text-[11px]">
                      Integrity risk: {lastTurnAnalysis.fraud_analysis.risk_level} ({lastTurnAnalysis.fraud_analysis.risk_score}){" "}
                      {Array.isArray(lastTurnAnalysis.fraud_analysis.flags) && lastTurnAnalysis.fraud_analysis.flags.length > 0
                        ? `| flags: ${lastTurnAnalysis.fraud_analysis.flags.join(", ")}`
                        : "| flags: none"}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </section>

            <ConceptGraph graph={session?.graph} />
          </div>

          {report ? (
            <section className="glass-panel rounded-2xl p-4">
              <h3 className="mb-2 text-lg font-semibold text-slate-900">Evaluation Report</h3>
              {reportSource ? (
                <div className="mb-2 text-xs text-slate-500">
                  Source: {reportSource}
                </div>
              ) : null}
              {reportData ? (
                <div className="space-y-3">
                  <div className="report-card rounded-xl p-3 text-sm text-slate-700">
                    <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Overall Assessment
                    </div>
                    <div>{reportData.overall_assessment || "Not provided."}</div>
                  </div>
                  <div className="report-card overflow-x-auto rounded-xl p-3">
                    <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Score Snapshot
                    </div>
                    <table className="w-full text-left text-xs text-slate-700">
                      <tbody>
                        <tr><td className="py-1 font-semibold">Concept Coverage</td><td>{reportData?.score_snapshot?.concept_coverage || "N/A"}</td></tr>
                        <tr><td className="py-1 font-semibold">Average Depth</td><td>{reportData?.score_snapshot?.average_depth || "N/A"}</td></tr>
                        <tr><td className="py-1 font-semibold">Average Confidence</td><td>{reportData?.score_snapshot?.average_confidence || "N/A"}</td></tr>
                        <tr><td className="py-1 font-semibold">Signal Quality</td><td>{reportData?.score_snapshot?.signal_quality || "N/A"}</td></tr>
                      </tbody>
                    </table>
                  </div>
                  <div className="report-card overflow-x-auto rounded-xl p-3">
                    <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Concept Evidence Matrix
                    </div>
                    <table className="w-full text-left text-xs text-slate-700">
                      <thead>
                        <tr className="border-b border-[var(--border)]">
                          <th className="py-1">Concept</th>
                          <th className="py-1">Depth</th>
                          <th className="py-1">Confidence</th>
                          <th className="py-1">Evidence</th>
                          <th className="py-1">Verdict</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(reportData.concept_matrix || []).slice(0, 12).map((row, idx) => (
                          <tr key={`${row.concept}-${idx}`} className="border-b border-[var(--border)]/50">
                            <td className="py-1">{row.concept || "-"}</td>
                            <td className="py-1">{row.depth || "-"}</td>
                            <td className="py-1">{row.confidence || "-"}</td>
                            <td className="py-1">{row.evidence || "-"}</td>
                            <td className="py-1">{row.verdict || "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="grid gap-3 md:grid-cols-3">
                    <div className="report-card rounded-xl p-3 text-xs text-slate-700">
                      <div className="mb-1 font-semibold text-slate-900">Strengths</div>
                      <ul className="space-y-1">
                        {(reportData.strengths || []).slice(0, 5).map((item, idx) => (
                          <li key={`s-${idx}`}>• {item}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="report-card rounded-xl p-3 text-xs text-slate-700">
                      <div className="mb-1 font-semibold text-slate-900">Gaps</div>
                      <ul className="space-y-1">
                        {(reportData.gaps || []).slice(0, 5).map((item, idx) => (
                          <li key={`g-${idx}`}>• {item}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="report-card rounded-xl p-3 text-xs text-slate-700">
                      <div className="mb-1 font-semibold text-slate-900">Recommendation</div>
                      <div><span className="font-semibold">Decision:</span> {reportData?.recommendation?.decision || "N/A"}</div>
                      <div><span className="font-semibold">Confidence:</span> {reportData?.recommendation?.confidence || "N/A"}</div>
                      <div className="mt-2">{reportData?.recommendation?.rationale || "No rationale provided."}</div>
                    </div>
                  </div>
                  <div className="report-card rounded-xl p-3 text-xs text-slate-700">
                    <div className="mb-1 font-semibold text-slate-900">Targeted Follow-up Questions</div>
                    <ul className="space-y-1">
                      {(reportData.follow_ups || []).slice(0, 6).map((item, idx) => (
                        <li key={`f-${idx}`}>• {item}</li>
                      ))}
                    </ul>
                  </div>
                  {reportData.integrity_signals ? (
                    <div className="report-card rounded-xl p-3 text-xs text-slate-700">
                      <div className="mb-1 font-semibold text-slate-900">Integrity Signals</div>
                      <div><span className="font-semibold">Average Risk:</span> {reportData.integrity_signals.average_risk_score}</div>
                      <div><span className="font-semibold">Max Risk:</span> {reportData.integrity_signals.max_risk_score}</div>
                      <div><span className="font-semibold">High-Risk Turns:</span> {reportData.integrity_signals.high_risk_turns}</div>
                      <div><span className="font-semibold">Top Flags:</span> {(reportData.integrity_signals.top_flags || []).join(", ") || "none"}</div>
                      <div className="mt-2">{reportData.integrity_signals.verdict}</div>
                    </div>
                  ) : null}
                  {reportData.context_signals ? (
                    <div className="report-card rounded-xl p-3 text-xs text-slate-700">
                      <div className="mb-1 font-semibold text-slate-900">Context Source Signals</div>
                      <div><span className="font-semibold">Source:</span> {reportData.context_signals.source || "n/a"}</div>
                      <div><span className="font-semibold">Mode:</span> {reportData.context_signals.mode || "n/a"}</div>
                      <div><span className="font-semibold">Used:</span> {reportData.context_signals.used ? "yes" : "no"}</div>
                      <div className="mt-1">{reportData.context_signals.status || ""}</div>
                    </div>
                  ) : null}
                </div>
              ) : (
                <pre className="max-h-[380px] overflow-y-auto whitespace-pre-wrap rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] p-3 text-sm text-slate-700">
                  {report}
                </pre>
              )}
            </section>
          ) : null}
          {activityEvents.length ? (
            <section className="glass-panel rounded-2xl p-4">
              <h3 className="mb-2 text-sm font-semibold text-slate-900">Localhost Activity</h3>
              <div className="max-h-[240px] overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] p-2 text-xs text-slate-600">
                {activityEvents.slice(0, 20).map((event, idx) => (
                  <div key={`${event.timestamp}-${idx}`} className="mb-1 rounded-md bg-white px-2 py-1">
                    [{event.status_code}] {event.method} {event.path} - {event.elapsed_ms}ms
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </main>
      )}
    </div>
  );
}
