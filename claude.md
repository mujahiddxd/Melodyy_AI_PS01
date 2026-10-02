# Hinglish Order Desk — rules for Claude

- Source of truth: IMPLEMENTATION_PLAN.md (what to build, stage by stage) and DESIGN.md (how the UI looks). Follow both exactly.
- Build ONE stage at a time. Never start the next stage until I say so.
- Monorepo: /backend (FastAPI, SQLAlchemy, Alembic, PostgreSQL) and /frontend (Next.js App Router, TypeScript, Tailwind).
- Keep API_CONTRACT.md updated: every endpoint's request/response JSON, error codes, auth headers. Frontend and backend must match it exactly.
- The app must run after every stage. Integrate frontend + backend + DB in every stage; no disconnected screens.
- LLM output is untrusted: validate with Pydantic; prices, stock and totals come only from the DB; inventory deducted only on confirm, in a transaction.
- No secrets in the frontend. Keys only in backend/.env (never commit .env; keep .env.example updated).
- Khata/udhaar/credit is OUT OF SCOPE. Do not build any part of it.
- Every screen needs loading, error and empty states. Label mocked features "DEMO / MOCK".
- I am on Windows. Give commands that work in PowerShell.
- At the end of each stage: run the stage's completion checklist, report pass/fail for each item, list the exact commands for me to run and test it, then stop.
- If you're short on time, apply the stage's "If behind" cuts instead of leaving things half-built.
- Before starting any stage that needs an external key or service, list the exact backend/.env variables it needs and STOP until I confirm they're set. Never invent keys and never ask me to paste keys into chat. If I say "use mock", proceed with the mock mode and label it in the UI.