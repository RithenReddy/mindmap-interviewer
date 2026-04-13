import { useMemo, useRef, useState } from "react";

const LINKEDIN_URL = "https://www.linkedin.com/in/alex-growth-lead";
const JOB_URL = "https://careers.gumloop.com/jobs/head-of-marketing";
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function initialConcepts() {
  return [
    { name: "PLG Strategy", depth: 0 },
    { name: "Funnel Optimization", depth: 0 },
    { name: "Messaging Clarity", depth: 0 },
    { name: "Budget Allocation", depth: 0 },
  ];
}

function initialChecklist() {
  return [
    { id: "c1", label: "Diagnose PLG bottleneck", done: false },
    { id: "c2", label: "Design testable experiment plan", done: false },
    { id: "c3", label: "Translate technical capabilities", done: false },
    { id: "c4", label: "Channel and budget tradeoffs", done: false },
  ];
}

export default function UsecasesPage() {
  const stageRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(2);
  const [status, setStatus] = useState("Run the curated replay to simulate the full product journey.");
  const [cursor, setCursor] = useState({ x: 120, y: 90, down: false });
  const [linkedinValue, setLinkedinValue] = useState("");
  const [jobValue, setJobValue] = useState("");
  const [step, setStep] = useState("onboarding");
  const [messages, setMessages] = useState([]);
  const [conceptDepth, setConceptDepth] = useState(initialConcepts());
  const [checklist, setChecklist] = useState(initialChecklist());
  const [integrityRisk, setIntegrityRisk] = useState("low");
  const [reportVisible, setReportVisible] = useState(false);
  const [reasoning, setReasoning] = useState("Reasoning trace appears as the interview progresses.");
  const [contextSignal, setContextSignal] = useState("slack (mock) - priming...");
  const [activity, setActivity] = useState([]);
  const [parallelContextUsed, setParallelContextUsed] = useState("none");

  const scaledWait = (ms) => wait(Math.max(28, Math.floor(ms / speed)));

  const points = useMemo(
    () => ({
      linkedin: { x: 160, y: 190 },
      job: { x: 160, y: 244 },
      fetch: { x: 215, y: 302 },
      startInterview: { x: 230, y: 360 },
      chatInput: { x: 575, y: 468 },
      sendBtn: { x: 875, y: 468 },
      reportBtn: { x: 875, y: 152 },
      activity: { x: 1000, y: 286 },
    }),
    []
  );

  function resetReplay() {
    setLinkedinValue("");
    setJobValue("");
    setMessages([]);
    setReportVisible(false);
    setIntegrityRisk("low");
    setStep("onboarding");
    setConceptDepth(initialConcepts());
    setChecklist(initialChecklist());
    setReasoning("Reasoning trace appears as the interview progresses.");
    setContextSignal("slack (mock) - priming...");
    setActivity([]);
    setParallelContextUsed("none");
  }

  function pushActivity(line) {
    setActivity((prev) => [`${new Date().toLocaleTimeString()} - ${line}`, ...prev].slice(0, 8));
  }

  async function moveTo(point, click = false, pause = 160) {
    setCursor((prev) => ({ ...prev, x: point.x, y: point.y, down: click }));
    await scaledWait(pause);
    if (click) {
      setCursor((prev) => ({ ...prev, down: false }));
      await scaledWait(120);
    }
  }

  async function typeInto(setter, value, cps = 18) {
    const charDelay = Math.max(15, Math.floor(1000 / cps));
    for (let i = 1; i <= value.length; i += 1) {
      setter(value.slice(0, i));
      await scaledWait(charDelay);
    }
  }

  async function runReplay() {
    if (playing) return;
    setPlaying(true);
    resetReplay();
    setStatus("Stage 1/5: Capturing candidate and role context...");

    await moveTo(points.linkedin, true);
    await typeInto(setLinkedinValue, LINKEDIN_URL, 28);

    await moveTo(points.job, true);
    await typeInto(setJobValue, JOB_URL, 28);

    await moveTo(points.fetch, true, 220);
    pushActivity("[200] POST /api/onboarding/scrape - 514ms");
    setContextSignal("slack (mock) - active");
    await scaledWait(460);

    setStatus("Stage 2/5: Review + prime adaptive interview...");
    await moveTo(points.startInterview, true, 240);
    pushActivity("[200] POST /api/interview/start - 1122ms");
    setStep("interview");
    setMessages([
      {
        role: "assistant",
        text: "Hey Alex, good to meet you. I noticed your PLG background. How do you diagnose conversion drop-offs before proposing fixes?",
      },
    ]);
    setReasoning("Why this question: Validate root-cause rigor before jumping to tactics.");
    await scaledWait(360);

    setStatus("Stage 3/5: Adaptive interview with live concept intelligence...");
    await moveTo(points.chatInput, true);
    const answerOne =
      "I segment by activation cohorts, map drop-offs by funnel stage, and prioritize by impact-confidence-effort before experiments.";
    await typeInto(
      (value) =>
        setMessages((prev) => [
          prev[0],
          { role: "user", text: value },
        ]),
      answerOne,
      38
    );
    await moveTo(points.sendBtn, true);
    pushActivity("[200] POST /api/interview/respond - 842ms");
    setParallelContextUsed("search");
    setConceptDepth((prev) => prev.map((item, idx) => ({ ...item, depth: idx < 2 ? 2 : item.depth })));
    setChecklist((prev) => prev.map((item, idx) => (idx < 2 ? { ...item, done: true } : item)));
    setMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        text: "Great structure. What exact experiment would you run first, and what success threshold confirms it worked?",
      },
    ]);
    setReasoning("Why this question: Candidate showed framework strength; now probing execution specificity.");
    await scaledWait(500);

    setStatus("Stage 4/5: Integrity layer catches suspicious response behavior...");
    await moveTo(points.chatInput, true);
    const pastedAnswer =
      "I would execute a holistic experimentation stack across onboarding, lifecycle nudges, and pricing page intent scoring to maximize funnel elasticity.";
    setMessages((prev) => [...prev, { role: "user", text: pastedAnswer }]);
    setIntegrityRisk("high");
    pushActivity("[200] Integrity analyzer flagged high_paste_ratio");
    await scaledWait(540);
    setConceptDepth((prev) => prev.map((item, idx) => ({ ...item, depth: idx < 3 ? 3 : 2 })));
    setChecklist((prev) => prev.map((item, idx) => (idx < 3 ? { ...item, done: true } : item)));
    setMessages((prev) => [
      ...prev,
      {
        role: "assistant",
        text: "Final probe: How would you allocate budget across channels if CAC rises unexpectedly?",
      },
    ]);
    setReasoning("Why this question: Added finance-pressure constraint to test decision quality under uncertainty.");
    await scaledWait(620);

    setStatus("Stage 5/5: Generating explainable evaluation report...");
    setStep("report");
    await moveTo(points.activity, true, 200);
    await moveTo(points.reportBtn, true, 260);
    pushActivity("[200] GET /api/interview/session/report - 1318ms");
    setChecklist((prev) => prev.map((item) => ({ ...item, done: true })));
    setReportVisible(true);
    await scaledWait(650);

    setStatus("Replay complete. Full product stack demonstrated.");
    setPlaying(false);
  }

  return (
    <div className="app-shell mx-auto min-h-screen px-4 py-8 md:px-8">
      <header className="glass-panel mb-5 rounded-3xl p-6">
        <p className="luxury-kicker text-xs">Use Case Replay</p>
        <h1 className="brand-title mt-2 text-4xl font-bold text-slate-900">/usecases Curated Demo Session</h1>
        <p className="mt-2 text-sm text-slate-600">
          One-click cinematic walkthrough of onboarding, adaptive interview, explainability, integrity flags, activity feed, and final report.
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="btn-primary gumloop-button-shadow rounded-lg px-4 py-2 text-xs font-bold"
            disabled={playing}
            onClick={runReplay}
          >
            {playing ? "Running curated replay..." : "Run Curated Replay"}
          </button>
          <label className="text-xs text-slate-500">
            Demo Speed
            <select
              className="app-input ml-2 rounded-md px-2 py-1 text-xs"
              value={speed}
              onChange={(event) => setSpeed(Number(event.target.value))}
              disabled={playing}
            >
              <option value={1.5}>1.5x</option>
              <option value={2}>2x</option>
              <option value={3}>3x</option>
              <option value={4}>4x</option>
            </select>
          </label>
          <a href="/" className="btn-tertiary rounded-lg px-3 py-2 text-xs font-semibold">
            Back to App
          </a>
          <span className="stat-chip rounded-full px-3 py-1 text-xs">{status}</span>
        </div>
      </header>

      <section ref={stageRef} className="replay-stage glass-panel relative overflow-hidden rounded-3xl p-4">
        <div
          className={`replay-cursor ${cursor.down ? "down" : ""}`}
          style={{ left: `${cursor.x}px`, top: `${cursor.y}px` }}
        />

        <div className="grid gap-4 xl:grid-cols-[1fr,1.2fr,0.95fr]">
          <div className="space-y-4">
            <div className="replay-card rounded-2xl p-4">
              <h2 className="text-sm font-semibold text-slate-900">Onboarding + Context</h2>
              <p className="mt-1 text-xs text-slate-500">Source capture and context priming</p>
              <div className="mt-3 space-y-2">
                <input className="app-input w-full rounded-lg px-3 py-2 text-xs" readOnly value={linkedinValue} placeholder="LinkedIn URL" />
                <input className="app-input w-full rounded-lg px-3 py-2 text-xs" readOnly value={jobValue} placeholder="Job URL" />
                <button type="button" className="btn-secondary w-full rounded-lg px-3 py-2 text-xs font-bold">
                  Fetch + Prime Interview
                </button>
              </div>
              <div className="mt-3 rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] p-2 text-xs text-slate-600">
                Context signals: <span className="font-semibold">{contextSignal}</span>
              </div>
            </div>

            <div className="replay-card rounded-2xl p-4">
              <h3 className="text-sm font-semibold text-slate-900">Dynamic Checklist</h3>
              <div className="mt-2 space-y-2 text-xs">
                {checklist.map((item) => (
                  <div key={item.id} className="flex items-center gap-2 rounded-md border border-[var(--border)] bg-[var(--surface-muted)] px-2 py-1.5">
                    <span>{item.done ? "✅" : "⬜"}</span>
                    <span className="text-slate-700">{item.label}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div className="replay-card rounded-2xl p-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-900">Adaptive Interview</h2>
                <button type="button" className="btn-tertiary rounded-md px-2 py-1 text-[10px] font-semibold">
                  Generate Report
                </button>
              </div>
              <div className="mt-2 rounded-md border border-[var(--border)] bg-[var(--surface-muted)] px-2 py-1 text-[11px] text-slate-600">
                {reasoning}
              </div>
              <div className="mt-3 h-72 space-y-2 overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] p-3">
                {messages.length === 0 ? (
                  <div className="text-xs text-slate-500">Interview messages appear during replay.</div>
                ) : (
                  messages.map((msg, idx) => (
                    <div key={`${msg.role}-${idx}`} className={`rounded-lg px-2 py-2 text-xs ${msg.role === "assistant" ? "assistant-bubble" : "user-bubble"}`}>
                      {msg.text}
                    </div>
                  ))
                )}
              </div>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] p-2 text-xs text-slate-600">
                  Integrity risk: <span className="font-semibold">{integrityRisk}</span>
                </div>
                <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] p-2 text-xs text-slate-600">
                  Parallel context: <span className="font-semibold">{parallelContextUsed}</span>
                </div>
              </div>
            </div>

            <div className="replay-card rounded-2xl p-4">
              <h3 className="text-sm font-semibold text-slate-900">Live Concept Intelligence</h3>
              <div className="mt-3 space-y-2">
                {conceptDepth.map((concept) => (
                  <div key={concept.name} className="rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] p-2 text-xs text-slate-700">
                    <div className="flex items-center justify-between">
                      <span>{concept.name}</span>
                      <span className="font-semibold">Depth {concept.depth}/3</span>
                    </div>
                    <div className="mt-1 h-1.5 rounded-full bg-slate-300/30">
                      <div className="h-full rounded-full bg-gradient-to-r from-pink-500 via-amber-400 to-emerald-400" style={{ width: `${(concept.depth / 3) * 100}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div className="replay-card rounded-2xl p-4">
              <h3 className="text-sm font-semibold text-slate-900">Localhost Activity Feed</h3>
              <div className="mt-2 h-40 space-y-1 overflow-y-auto rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] p-2 text-[11px] text-slate-600">
                {activity.length ? activity.map((item, idx) => <div key={`${item}-${idx}`}>{item}</div>) : "Waiting for replay..."}
              </div>
            </div>

            <div className="replay-card rounded-2xl p-4">
              <h3 className="text-sm font-semibold text-slate-900">Evaluation Report</h3>
              {reportVisible ? (
                <div className="mt-2 space-y-2 text-xs text-slate-700">
                  <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] p-2">
                    <div className="font-semibold">Overall Assessment</div>
                    Strong strategic signal with one high-risk authenticity event requiring review.
                  </div>
                  <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] p-2">
                    <div>Coverage: 4/4</div>
                    <div>Average Depth: 2.75</div>
                    <div>Average Confidence: 0.74</div>
                    <div>Decision: Hold with follow-up validation</div>
                  </div>
                  <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] p-2">
                    Context Source: slack (mock) | Integrity: high_paste_ratio
                  </div>
                </div>
              ) : (
                <div className="mt-2 rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] p-3 text-xs text-slate-500">
                  Report section appears at final replay stage.
                </div>
              )}
            </div>

            <div className="replay-card rounded-2xl p-4 text-xs text-slate-600">
              Replay Stage: <span className="font-semibold capitalize text-slate-800">{step}</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
