# ResumeForge architecture

This document describes the current system boundaries. It is intentionally smaller than a full design specification.

## Request flow

```
User
  ↓
Screening profile
  ↓
Resume source
  ↓
Preview / explicit import
  ↓
Canonical upload pipeline
  ↓
Processing job
  ↓
Parse
  ↓
Extract
  ↓
Deterministic scoring
  ↓
Duplicate detection
  ↓
Candidate
  ↓
Optional AI analysis
  ↓
Human review
  ↓
Human decision
  ↓
Audit
```

## Canonical ingestion

All resume sources eventually produce the same upload contract and enter the same pipeline.

This prevents a connector from accidentally becoming a second screening implementation.

Sources currently represented by the application:

- Manual upload
- Gmail connector architecture
- Mock source for deterministic tests
- LinkedIn unavailable state

## Data boundaries

### Source layer

Responsible for:

- discovering candidate messages/files
- applying source filters
- previewing matches
- idempotency
- import decisions
- source audit events

It does not score candidates.

### Processing layer

Responsible for:

- parsing supported file types
- extracting structured fields
- creating processing jobs
- retrying failed work
- preserving failure reasons

### Screening layer

Responsible for:

- configurable criteria
- deterministic component scoring
- recommendation labels
- missing requirements

### AI layer

AI analysis is optional and advisory.

The AI layer does not own deterministic scoring or human decisions.

### Human review layer

Human decisions are authoritative:

- Interview
- Shortlist
- Hold
- Close

A recommendation is evidence for review, not an instruction to the reviewer.

## Truthfulness rules

The application should distinguish:

- successful execution
- failed execution
- missing information
- unavailable integrations
- unconfigured AI
- human decisions

A missing integration is not represented as a successful integration.

A missing resume field is not inferred.

A failed processing job is not converted into a successful candidate.

## Security boundary

Resume files are untrusted input.

The system must:

- never execute uploaded files
- whitelist supported resume formats
- keep runtime data out of git
- keep credentials out of audit records
- avoid placing real candidate data in fixtures
- treat external connectors as read-only unless an explicit import action occurs

## Current verification boundary

The repository has acceptance-tested the main local workflow, including batch ingestion, candidate review, human decisions, source preview/import, duplicate handling, retry behavior, export, audit, and responsive UI.

External Gmail authentication remains an explicit verification gap.

## Design rule

When a feature can be made deterministic, make it deterministic.

Use AI where judgment over unstructured text is actually useful. Keep routing, state transitions, scoring, idempotency, permissions, and verification in code.
