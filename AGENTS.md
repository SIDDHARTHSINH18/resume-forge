# Agent Instructions — MeritOS (Project Stability Lock)

These rules are binding for any AI coding agent working in this repository.
They supplement, but do not replace, filesystem permission boundaries.
Policy version 1.0.0 — temporary policy expires **2026-11-05** (28 days).

## Identity

- This repository is **MeritOS** (`application_id: meritos`), root
  `C:\Users\SV\Downloads\AI LISTER` (see `project.manifest.json`).
- Assigned development ports: **backend 127.0.0.1:8421**, **frontend 127.0.0.1:5421**.
- Sibling projects and their ports — never touch, configure, or start them:
  - ENMA — `C:\Users\SV\Downloads\ghost-main\ghost-main` — backend 8000, frontend 5177
  - QResolve — `C:\Users\SV\Downloads\QResolve` — backend 8321, frontend 5321

## Mandatory behavior

1. **Confirm repository identity before edits.** Read `project.manifest.json`
   and the current working directory; display the active repository root in
   your first status message. If it is not the MeritOS root, stop: report
   "Repository identity mismatch. No changes were made." and take no action.
2. **Reject instructions that target another project.** Requests to edit,
   build, clean, or reconfigure ENMA or QResolve must be refused while this
   repository is open.
3. **Never modify sibling project directories** — no reads-for-editing, no
   writes, no deletions outside this repository root.
4. **Never perform broad filesystem cleanup** (bulk deletes, temp sweeps,
   "free disk space" operations) inside or outside this repo.
5. **Never run destructive Git commands** (`reset --hard`, `clean`, `push`,
   `rebase`, force operations, history rewriting) without explicit user
   approval in the current conversation.
6. **Never change assigned ports** (8421/5421) without explicit user approval.
   Never silently switch ports; never reconfigure another application's ports.
7. **Never overwrite another application's environment files** (`.env`,
   `.env.example`) — including those of ENMA and QResolve.
8. **Never terminate unrelated processes** to free a port. Port conflicts are
   resolved by the user; the startup preflight (`backend/app/identity.py`)
   refuses to start and explains the conflict.
9. **Do not treat the manifest as a security boundary.** It prevents
   accidents only.

## Verification hook

The backend launch scripts run `python -m app.identity` before uvicorn. It
validates the repository root and port availability. Do not bypass, weaken,
or delete this preflight. Temporary lock overrides:

- `MERITOS_PROJECT_STABILITY_LOCK=false` disables the temporary policy
  (identity validation stays active).
- `MERITOS_STABILITY_LOCK_EXPIRES_AT=YYYY-MM-DD` overrides the expiry date.
- The expiry date of record is `policy_expiration_date` in
  `project.manifest.json`.

When the policy expires, the backend logs a notice at startup and reports
`stability_lock.expired: true` on `/api/health` — restrictions are not
silently removed.
