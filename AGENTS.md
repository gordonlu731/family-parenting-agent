# Family parenting assistant

One household, one child. Current baseline: 0.2.3. Read README.md and docs/STATUS.md before changing behavior; docs/HANDOFF.md lists pending work.

## Development

- Python 3.12; install requirements.lock. Node 22.12+ or 24; npm ci --ignore-scripts.
- Build with npm run build, then run npm test for backend changes. Use temporary databases and mocked HTTP in tests; do not require or call real model APIs for automated tests.
- Frontend: React/TypeScript in frontend/. Backend: FastAPI and SQLite in backend/.
- scripts/deploy.py check is read-only. configure privately creates .env without overwriting it. check_model.py --call-model explicitly calls a potentially billable API.

## Product boundaries

- Meals that were actually eaten and planned menus are separate data. AI returns private drafts; only explicit human confirmation commits records or publishes menus.
- Authorization, household isolation, allergy-name checks, idempotency, duplicate-meal checks and version checks are server responsibilities. Preserve them when adding tools or voice.
- Menu generation currently supports confirmed profiles aged at least 12 months. Allergy-name matching is incomplete; do not label recipes as medically verified or guaranteed safe.
- Personal chats and drafts are private; confirmed records and menus are shared. Never put API keys or login tokens in browser code.
- VoiceTest is local recording/playback only. Do not describe it as ASR, TTS or voice conversation.

## Operations and continuity

- This source repository is public by the owner's explicit choice. Keep it separate from quantitative research repositories; household data and credentials must remain private.
- Never commit .env, databases, backups, family exports, recordings or production credentials. Use fictitious data only.
- Read-only inspection and local implementation may proceed within the task. Avoid modifying unrelated ECS services. Never claim deployed, live-model verified, or WeChat tested without observing it.
- Existing migrations are immutable; add numbered migrations. Back up before upgrading an actual deployment. Preserve Compose project name and persistent volume; do not delete volumes to fix issues.
- Browser visual QA is pending because the previous managed preview failed with uv_interface_addresses. Follow the preview service's documented repair/recovery process, without bypasses.
- Update docs/STATUS.md and docs/VERIFICATION.md for meaningful changes. Distinguish mocked checks, real model evaluation, browser verification and deployment.
