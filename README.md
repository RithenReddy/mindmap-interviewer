# MindMap Interviewer (Tailwind UI + FastAPI)

## Run Backend

```bash
cd mindmap-interviewer
python3 -m pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

Required env vars:

- `ANTHROPIC_API_KEY`
- `GUMLOOP_MCP_TOKEN` (needed for Apollo + Firecrawl scrape)

## Run Frontend

```bash
cd mindmap-interviewer/web
npm install
npm run dev
```

Optional env var:

- `VITE_API_BASE` (defaults to `http://localhost:8000`)

## Deploy Everything on Vercel (Single Project)

This repo is configured with `vercel.json` so one Vercel project serves both:
- FastAPI backend from `server.py` on `/api/*`
- React frontend from `web/dist`

### Steps

1. Import the GitHub repo into Vercel.
2. Keep root directory as repository root (`mindmap-interviewer`).
3. Add environment variables (Production + Preview):
   - `ANTHROPIC_API_KEY`
   - `ENABLE_SLACK_CONTEXT=1`
   - `SLACK_CONTEXT_MODE=mock`
4. Deploy.

### Notes

- Frontend automatically calls same-origin API in production, so `VITE_API_BASE` is optional on Vercel.
- Do not add secrets with `VITE_` prefix.
- Gumloop variables are optional and only needed if you want live Apollo/Firecrawl scraping or Gumloop agent paths:
  - `GUMLOOP_MCP_TOKEN`
  - `GUMLOOP_API_KEY`
  - `GUMLOOP_USER_ID`
  - `GUMLOOP_INTERVIEW_AGENT_ID`
  - `GUMLOOP_REPORT_AGENT_ID`
