function scoreColor(score) {
  if (score >= 3) return "score-success border border-emerald-300/40";
  if (score === 2) return "score-warning border border-amber-300/40";
  if (score === 1) return "score-danger border border-rose-300/40";
  return "score-idle border border-[var(--border)]";
}

function importanceBadge(importance) {
  if (importance === "critical") return "text-rose-700";
  if (importance === "important") return "text-amber-700";
  return "text-slate-500";
}

export default function ConceptGraph({ graph }) {
  if (!graph?.nodes?.length) {
    return (
      <div className="glass-panel rounded-2xl p-6 text-slate-500">
        Graph appears once interview starts.
      </div>
    );
  }

  return (
    <div className="glass-panel rounded-2xl p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-slate-900">Live Concept Intelligence</h3>
        <div className="stat-chip rounded-full px-2 py-1 text-[11px]">
          Explored {graph.stats.explored}/{graph.stats.total}
        </div>
      </div>
      <div className="grid gap-2 md:grid-cols-2">
        {graph.nodes
          .slice()
          .sort((a, b) => a.depth_score - b.depth_score)
          .map((node) => (
            <div
              key={node.id}
              className={`rounded-xl border p-3 ${scoreColor(node.depth_score)}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-slate-900">{node.name}</div>
                  <div className="text-xs text-slate-500">{node.category}</div>
                </div>
                <div className="stat-chip rounded-full px-2 py-1 text-xs font-bold">
                  {node.depth_score}/3
                </div>
              </div>
              <div className="mt-2 flex items-center justify-between text-xs">
                <span className={importanceBadge(node.importance)}>{node.importance}</span>
                {node.parent_id ? <span className="text-slate-500">parent: {node.parent_id}</span> : null}
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
