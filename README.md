# ResumeForge

<details>
<summary><strong>⚡ Quick navigation</strong></summary>

**Explore:** [What it is](#what-it-is) · [Architecture](#architecture) · [Capabilities](#current-capabilities) · [Engineering evidence](#engineering-evidence) · [Security](#security-boundary) · [Run locally](#development)

</details>

**Evidence-first candidate screening with human-controlled decisions.**

ResumeForge is a local-first screening platform for recruitment and college admissions. It turns resumes into structured evidence, applies a deterministic screening model, optionally adds AI analysis, and leaves the final decision to a human reviewer.

The design goal is simple:

> **Make screening easier to inspect, not easier to automate blindly.**

## What it does

- Ingests PDF, DOCX, and TXT resumes through one canonical pipeline
- Extracts structured candidate information without guessing missing data
- Scores candidates with six deterministic, configurable components
- Supports recruitment and college screening profiles
- Shows requirement-level evidence and missing requirements
- Adds optional AI analysis without making the AI the decision-maker
- Supports human decisions: Interview, Shortlist, Hold, Close
- Records notes and actions in an audit trail
- Detects potential duplicates without silently deleting candidates
- Processes batches with live progress and honest failure states
- Retries failed processing jobs
- Exports candidate data to CSV
- Supports resume-source ingestion with **preview → review → explicit import**
- Includes Gmail connector architecture using the official OAuth/API path
- Keeps LinkedIn unavailable rather than scraping or inventing data
- Runs locally with SQLite and local files

## Architecture

The important boundary is the ingestion pipeline. Different sources do not get different screening logic.

```
Manual upload ─┐
Gmail ─────────┤
Mock source ───┤
               ↓
        Source / Preview
               ↓
        Explicit Import
               ↓
        Canonical Pipeline
               ↓
        Parse → Extract
               ↓
        Deterministic Score
               ↓
        Duplicate Detection
               ↓
        Candidate + Evidence
               ↓
       Optional AI Analysis
               ↓
          Human Review
               ↓
          Human Decision
```

The system recommendation and the human decision are separate records.

```
Recommendation
     ≠
Human decision
```

That separation is intentional. ResumeForge is not an autonomous hiring or rejection system.

## Scoring model

The default screening score is composed of six transparent components:

| Component | Weight |
| --- | ---: |
| Academic | 25% |
| Required skills | 30% |
| Relevant experience | 20% |
| Projects | 15% |
| Certifications | 5% |
| Completeness | 5% |

Profiles can configure their own screening criteria and thresholds.

Missing information is reported as **Not found** rather than inferred.

## AI boundary

AI is optional.

Without an AI provider, the deterministic screening pipeline still works.

When enabled, AI is used for analysis and explanation. It does not control ingestion, override deterministic evidence, or make the final candidate decision.

The repository supports provider-agnostic integration for:

- None / deterministic-only
- OpenAI-compatible endpoints
- Groq
- Google Gemini
- Local endpoints
- Mock provider for deterministic tests

The mock provider is test infrastructure, not a claim of model performance.

## Resume sources

```
SOURCE
  ↓
PREVIEW
  ↓
REVIEW
  ↓
IMPORT
  ↓
PROCESSING
  ↓
RESULTS
```

Preview does not silently import resumes.

Gmail uses the official Gmail API with OAuth 2.0 and read-only access. LinkedIn web scraping is deliberately not implemented.

Only PDF, DOCX, and TXT attachments enter the resume pipeline. Unsupported attachments are ignored and never executed.

## Security and privacy

Resumes contain personal information, so runtime data stays outside the repository.

The repository must not contain:

- real resumes
- real candidate records
- real Gmail messages
- OAuth tokens
- API keys
- passwords
- production credentials

Local runtime state, uploads, databases, configuration, and generated demo data are git-ignored.

Gmail OAuth credentials are currently stored in local configuration rather than an OS keychain. That is a documented limitation, not hidden behind the README.

## Engineering choices

A few decisions are deliberately conservative:

- **Deterministic logic before AI** when a rule can be expressed in code.
- **One ingestion path** instead of source-specific screening behavior.
- **Human authority** over recommendation output.
- **Explicit uncertainty** instead of fabricated completeness.
- **Idempotent imports** so rescanning does not duplicate candidates.
- **Auditability** for important actions.
- **Failure visibility** instead of pretending a failed job completed.

## Stack

- Python 3.12+
- FastAPI
- SQLite / WAL
- pypdf
- python-docx
- React 19
- TypeScript
- Vite
- Vitest

## Run locally

### Backend

```bat
cd backend
python -m venv .venv
.venv\\Scripts\\python.exe -m pip install -r requirements.txt
.venv\\Scripts\\python.exe -m pytest
```

### Frontend

```bat
cd frontend
npm ci
npm test
npm run build
```

### Application

For the production-style local run:

```bat
frontend\\npm run build
scripts\\run_backend.bat
```

Then open:

```
http://127.0.0.1:8100
```

## Verification

The latest M3 acceptance run on the actual application reported:

- Backend: **119 passed**
- Frontend: **23 passed**
- TypeScript: **passed**
- Production build: **passed**
- Responsive checks: **320 / 375 / 544 / 768 / 1024 / desktop**
- Real browser workflow: profile creation, resume intake, screening, search/filter/sort, candidate review, human decisions, retry, CSV export, audit feed
- Resume source workflow: preview, explicit import, repeated-scan idempotency, duplicate detection, unsupported-file handling

These are acceptance results for the current development state, not a claim of universal production readiness.

## Known limitations

- Live Gmail OAuth has not been verified against a real external mailbox in the acceptance run.
- Gmail credentials/tokens are stored in local plaintext configuration rather than an OS keychain.
- Accessibility verification is an acceptance-tested subset, not a full WCAG compliance claim.
- Two low-priority UI/serving issues remain documented in the M3 acceptance notes.

## Project structure

```
backend/
frontend/
scripts/
tests/
```

See [docs/architecture.md](docs/architecture.md) for the system boundaries and data flow.

## License

MIT


<details>
<summary><strong>👀 Reading this repository</strong></summary>

If you have only one minute, read the opening principle, then inspect the architecture and verification/testing sections. The project is intentionally documented around **what the system can demonstrate**, not what it is intended to become.

</details>
