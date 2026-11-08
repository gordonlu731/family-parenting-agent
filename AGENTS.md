# Family parenting assistant

One household, one child. Current application baseline: 0.3.0. Read README.md, docs/STATUS.md, docs/CORE_SCENARIOS.md and docs/HANDOFF.md before changing behavior. docs/ROADMAP.md tracks executable tasks; docs/DECISIONS.md distinguishes confirmed choices from proposals.

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
- Pantry changes require explicit confirmation and optimistic revisions. Published menus, feeding records and shopping reads never consume stock. Cooked food, stale records, unknown quantities and incompatible units must not be silently treated as sufficient raw stock.
- VoiceTest is local recording/playback only. Do not describe it as ASR, TTS or voice conversation.

## Operations and continuity

- This source repository is public by the owner's explicit choice. Keep it separate from quantitative research repositories; household data and credentials must remain private.
- Never commit .env, databases, backups, family exports, recordings or production credentials. Use fictitious data only.
- Read-only inspection and local implementation may proceed within the task. Avoid modifying unrelated ECS services. Never claim deployed, live-model verified, or WeChat tested without observing it.
- Existing migrations are immutable; add numbered migrations. Back up before upgrading an actual deployment. Preserve Compose project name and persistent volume; do not delete volumes to fix issues.
- Browser visual QA is pending because the previous managed preview failed with uv_interface_addresses. Follow the preview service's documented repair/recovery process, without bypasses.
- Update docs/STATUS.md and docs/VERIFICATION.md for meaningful changes. Distinguish mocked checks, real model evaluation, browser verification and deployment.

## Required project continuity

- At the start of a task, inspect git status, fetch the target branch, and reconcile local changes with the remote without losing uncommitted work. Do not assume a previous chat, local ZIP, cached checkout or this version label is current.
- GitHub is the source of truth for shared code, requirements and progress. Keep this project's code and documentation together in this repository; do not copy quantitative-project code or private household data into it.
- Update the corresponding documentation in the same change as the work: CORE_SCENARIOS for product requirements, DECISIONS for confirmed choices and unresolved proposals, ROADMAP for task status, STATUS for the current snapshot, VERIFICATION for observed checks, and HANDOFF for the next concrete task. Keep README links and these instructions consistent.
- Do not label an assistant's suggestion as a user-approved requirement. Do not label planned, implemented, mocked-tested, real-model-tested and deployed states interchangeably. Explicitly preserve unknowns and blockers.
- Record the application version separately from documentation updates and Git commit identity. Documentation-only changes do not bump the application version. Record releases in CHANGELOG.md when behavior changes.
- Before publishing, review the diff for real family information or secrets; run checks appropriate to the change. Use normal commits and verify the remote branch after pushing. Never force-update main or overwrite concurrent work.
- End each task with a concise account of what changed, verification limits and next work; link to the relevant GitHub files or commit. If pushing is blocked, state that changes remain local instead of claiming they were saved to GitHub.
