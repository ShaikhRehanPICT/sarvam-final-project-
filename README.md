# OSINT Fusion Workbench (Hackathon MVP)

A local-first, analyst-in-the-loop demo for **public or explicitly authorized** documents and synthetic/demo audio. It extracts candidate entities and relationships, displays a knowledge graph, flags cross-source patterns for review, and preserves evidence provenance.

## Safety and scope
- Do not upload intercepted/private communications, leaked personal data, sealed police records, or material you are not authorized to process.
- The demo does not identify suspects, predict criminality, track private individuals, or make operational decisions.
- Confidence is an evidence-completeness heuristic, not the probability that a claim is true.
- Every AI extraction is a candidate. An analyst must approve or reject it.

## Architecture
- `frontend/`: React + Vite + Cytoscape graph
- `backend/`: FastAPI, SQLite, Sarvam AI SDK
- `backend/.env`: API key (never commit)
- API: `/api/documents`, `/api/audio/transcribe`, `/api/analyze/{document_id}`, `/api/graph`, `/api/signals`, `/api/reviews`

## Requirements
Android + Termux, Python 3.11+ (Termux package), Node.js LTS, Git.
A Sarvam API key is needed for live AI features. The UI and demo dataset work without one.

## Run locally
Open two Termux sessions.

### Backend
```bash
cd ~/osint-fusion-workbench/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env   # set SARVAM_API_KEY=...
uvicorn app:app --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd ~/osint-fusion-workbench/frontend
npm install
npm run dev -- --host 0.0.0.0
```
Open `http://127.0.0.1:5173` in Chrome.

If your phone is low on memory, use `npm run build` then serve the generated files through the backend as described below; dev mode is easier for development.

## Demo flow
1. Click **Load demo dataset**.
2. Select a source and click **Analyze**.
3. Review candidate entities and relationships.
4. Approve or reject candidates.
5. Open **Graph** and **Signals** to inspect links and evidence.
6. Upload only a public/authorized text/PDF file or a synthetic audio recording.

## Deployment
This MVP runs locally first. For a public demo, deploy the frontend and backend separately:
- Frontend: build with `npm run build`; deploy `frontend/dist` to Cloudflare Pages.
- Backend: deploy FastAPI to a Python host that supports persistent environment variables and SQLite/Postgres. SQLite on ephemeral serverless storage is not durable.
- Set `SARVAM_API_KEY` only in backend secrets. Set frontend `VITE_API_BASE` to your backend HTTPS URL before building.
- Do not expose the backend publicly without authentication, upload limits, rate limits, HTTPS, and a retention/deletion policy.
