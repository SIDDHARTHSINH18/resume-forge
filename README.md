# ResumeForge

**Evidence-First Candidate Screening**

ResumeForge is a local-first AI-assisted candidate screening platform that processes
resumes, extracts structured candidate information, evaluates candidates against
configurable criteria, provides evidence-backed screening results, and keeps the
final decision with a human reviewer.

> **AI recommendations are advisory.**
> **Human decisions are authoritative.**

ResumeForge is *not* an autonomous hiring or rejection system. It never advances,
rejects or closes a candidate on its own — it produces screening evidence, a
deterministic score, an optional AI-assisted analysis and a recommendation label.
A human reviewer makes every decision, and every action is recorded in an audit
trail.

## Main capabilities

- PDF / DOCX / TXT resume ingestion through one canonical pipeline
- Deterministic, explainable candidate scoring (six weighted components)
- Configurable recruitment *and* college screening profiles — nothing hardcoded
- Candidate search, filtering and sorting
- Candidate detail view with requirement-by-requirement evidence
- Missing-requirement detection (shown, never guessed)
- Optional AI-assisted analysis (clearly labelled, advisory only)
- Explicit human decisions (Move to Interview / Shortlist / Hold / Close) with reasons
- Human notes attached to candidates
- Full audit trail for every action
- CSV export (recorded in the audit log)
- Batch processing with live progress
- Failed-job retry with honest failure reasons
- Duplicate detection (flagged, never silently deleted)
- Resume Sources: automated intake with preview → explicit import
- Gmail connector architecture (official OAuth/API, read-only)
- Mock source for deterministic end-to-end testing
- Honest LinkedIn "Unavailable" state (no scraping, no inventing data)
- Responsive interface (320 → desktop verified)
- Accessibility features (acceptance-tested subset — see below)
- Local-first operation: SQLite + local files, no cloud dependency

## How screening works

1. **Ingest** — resumes arrive from manual upload, the mock source, or a connected
   Gmail account. Every file enters the *same* pipeline; there is no per-source
   shortcut.
2. **Parse & extract** — text is extracted and structured (education, skills,
   experience, projects, certifications, contact).
3. **Score deterministically** — six weighted components produce a transparent
   score. Missing information shows as "Not found" and scores zero; it is never
   guessed.
4. **Analyse (optional)** — if an AI provider is configured, an advisory analysis
   is added, labelled with provider, model and confidence. The app works fully
   without any provider.
5. **Review** — a human reviews the evidence and makes the final decision.

## Resume source model

```
Source
   ↓
Preview
   ↓
Review
   ↓
Explicit Import
   ↓
Processing
   ↓
Results
```

A preview only scans and classifies — nothing is downloaded or imported at that
step. Import is always an explicit button press, and imported files run through the
same pipeline as manual uploads (parsing, extraction, scoring, duplicate detection
and candidate creation are never bypassed).

- **Gmail** uses the official Gmail API with OAuth 2.0 and read-only access. No
  Google password is ever requested or stored, and no browser scraping is used.
  Gmail is **not** automatically connected — it requires your own Google Cloud
  OAuth client to be configured (see below).
- **LinkedIn** web scraping is **not implemented** and never will be. LinkedIn
  currently reports an honest "Unavailable" state: nothing is fetched and no data
  is invented.
- **Mock source** exists for deterministic testing (labelled `MOCK SOURCE`). It is a
  local fixture inbox — never a real mailbox and never presented as Gmail.
- **Manual upload** remains fully supported and is the canonical path every
  connector feeds into.

Mock data is testing infrastructure, not a production integration.

## AI safety and the human decision

ResumeForge deliberately separates:

```
System recommendation
        ≠
Human decision
```

The platform provides screening evidence and a deterministic score, plus optional
AI-assisted analysis and a recommendation label. It does **not** make autonomous
hiring decisions. The human reviewer makes the final call, and the interface states
this wherever a recommendation appears.

## Privacy

Resume files contain personal information. This repository must never contain:

- real resumes or real candidate data
- real Gmail messages
- OAuth tokens, API keys, passwords or production credentials

Only synthetic/demo data may be included where explicitly marked as testing/demo
data. The bundled demo generator creates synthetic, clearly-labelled fixtures at
runtime; they are git-ignored and never mixed with real applicants. Runtime state
(SQLite database, uploaded files, local configuration) is git-ignored as well.

## Tech stack

- **Backend:** Python 3.12+ (FastAPI, SQLite with WAL)
- **Frontend:** React 19 + TypeScript + Vite
- **Storage:** local SQLite + local files — nothing leaves your machine

## Requirements

- Windows (scripts provided) — Python 3.12+ and Node.js 20+ installed

## Setup

```bat
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

cd ..\frontend
npm install
```

## Run

Option A — production build served by the backend (single URL):

```bat
cd frontend
npm run build

cd ..\scripts
run_backend.bat
```

Open http://127.0.0.1:8100

Option B — development (hot reload):

```bat
scripts\run_backend.bat    rem API on http://127.0.0.1:8100
scripts\run_frontend.bat   rem UI on http://localhost:5273 (proxies /api)
```

## First steps

1. **Create a screening profile** — Screening Profiles → New profile. Choose the
   type (Recruitment or College), then configure required/preferred skills, weights,
   thresholds and the minimum academic requirement.
2. **Load resumes** — open the profile → Upload resumes, or use **Resume Sources**
   for automated intake (see above). PDF, DOCX and TXT are supported. Each file is
   parsed, deduplicated by content fingerprint and email, then scored on six
   weighted components. For evaluation, "Import demo resumes" generates ~14 clearly
   labelled synthetic files (including one deliberately broken PDF) and ingests them
   through the same pipeline — testing only.
3. **Process** — the Processing page shows live batch progress, failed files with
   reasons, and a Retry button per failed file.
4. **Review** — Candidates lists every parsed candidate with real filtering, search
   and sorting. Open a candidate for requirement-by-requirement match marks and
   scoring transparency (points / max per component), add notes, and record a
   decision (Move to Interview / Shortlist / Hold / Close). The Reviews page shows
   the queue of candidates still awaiting a human decision.
5. **Export** — Exports → Export CSV produces `Name, Email, Education, Academic
   score, Skill match, Experience, Overall match, Recommendation, Human decision,
   Status, Screening profile, Candidate ID`. Every export is recorded in the audit
   log.

## AI provider (optional)

Settings → AI provider. Options: None (deterministic only), OpenAI-compatible,
Groq, Google Gemini, Local endpoint, and Mock (testing only — returns deterministic
placeholder output, never a real score). API keys are stored locally and never
written to the audit log or exports.

## Connecting Gmail (optional, requires your own Google Cloud project)

1. In Google Cloud Console create a project and enable the **Gmail API**.
2. Configure the OAuth consent screen (External, testing is fine) and add your own
   Google account as a test user.
3. Create an OAuth client of type **Web application** and add this authorised
   redirect URI: `http://127.0.0.1:8100/api/sources/gmail/oauth/callback`
4. Paste the client ID and secret into Resume Sources → Gmail → Save OAuth client.
5. Click **Connect Gmail account**, sign in to Google and grant read-only access.
6. Back in the app, choose a screening profile, optionally filter by date range,
   sender or subject keywords, then Preview → Import.

Fetches are read-only and idempotent: re-scanning the same inbox never re-imports a
file. Attachment rules: only `.pdf`, `.docx` and `.txt` enter the pipeline;
everything else (`.zip`, `.exe`, `.bat`, …) is marked `IGNORED_UNSUPPORTED_TYPE` and
never executed or opened.

### Credential storage — known limitation

OAuth client secrets and Gmail access/refresh tokens are kept in
`backend/data/config.json`, a local plaintext JSON file (same store as the optional
AI provider keys), and are never written to SQLite or the audit log. This machine's
file permissions are the only protection; there is no OS keychain integration. If
that is not acceptable for you, do not connect Gmail — the rest of the app is fully
functional without it. Environment variables (`AILISTER_GMAIL_CLIENT_ID`,
`AILISTER_GMAIL_CLIENT_SECRET`, `AILISTER_GMAIL_REDIRECT_URI`) can override the
stored client for managed setups.

## Testing and verified status

```bat
cd backend
.venv\Scripts\python.exe -m pytest        rem 119 tests

cd ..\frontend
npm test                                  rem vitest, 23 tests
npm run build                             rem tsc typecheck + production build
```

Latest M3 acceptance results (verified on the running application):

- Backend: **119 passed**
- Frontend: **23 passed**
- TypeScript: **passed**
- Production build: **passed**
- Responsive: **320 / 375 / 544 / 768 / 1024 / desktop verified**
- M3 status: **READY TO FREEZE**

Accessibility is an **acceptance-tested subset** (keyboard navigation, skip link,
focus management, accessible names, contrast on sampled text, modal focus
behaviour) — not a claim of full WCAG compliance.

## Known low-priority items

Documented during M3 acceptance; classified **LOW** and non-blocking:

- **LOW-001** — Candidate detail AI card contains wording referring to
  deterministic scores as being "below" the AI card even though the layout places
  the scoring elsewhere.
- **LOW-002** — Static serving does not currently specify explicit Cache-Control
  behavior for index.html/assets.

## Data location

- SQLite database, uploaded files and config: `backend/data/` (git-ignored)
- Demo resume files: `backend/demo_data/` (git-ignored, regenerated at runtime)

## License

MIT — see [LICENSE](LICENSE).
