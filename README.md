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
