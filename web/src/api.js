const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `Request failed: ${response.status}`);
  }
  return payload;
}

export const api = {
  health: () => request("/api/health"),
  activity: (limit = 40) => request(`/api/activity?limit=${limit}`),
  scrape: (body) =>
    request("/api/onboarding/scrape", { method: "POST", body: JSON.stringify(body) }),
  startInterview: (body) =>
    request("/api/interview/start", { method: "POST", body: JSON.stringify(body) }),
  demoReplay: () => request("/api/interview/demo-replay", { method: "POST" }),
  respondInterview: (body) =>
    request("/api/interview/respond", { method: "POST", body: JSON.stringify(body) }),
  getReport: (sessionId) => request(`/api/interview/${sessionId}/report`),
};
