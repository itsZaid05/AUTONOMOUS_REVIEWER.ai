# Run and record the real-paper demonstration

Use the repaired branch and perform these steps on your own Windows PC with Docker Desktop and Ubuntu/WSL2. Localhost addresses below refer to that PC, not the managed cloud session. The cloud repair session passed 29 regression tests; five-real-paper acceptance remains incomplete and its Gemini request was blocked by the cloud network policy.

## 1. Start the local application

Enable Docker Desktop's WSL2 engine and integration with Ubuntu. Download this branch's ZIP or clone this branch, extract it into your WSL home directory, open a WSL terminal in the repository, then run:

```sh
bash scripts/start_demo.sh
```

The script creates `.verify-venv`, installs the host runner's dependencies, preserves or creates private `.env` settings, starts Compose, and retains the verified LNCS class. If Python venv is unavailable, install it with `sudo apt update` and `sudo apt install python3-venv` first. The initial Docker build downloads LibreOffice and TeX packages.

Open these links after startup:

| Service | Address |
|---|---|
| Dashboard | http://localhost:8501 |
| API health | http://localhost:8000/health |
| API documentation | http://localhost:8000/docs |
| n8n | http://localhost:5678 |
| Local captured email | http://localhost:8025 |

## 2. Configure private values before recording

Edit `.env` locally with an editor. Do not print it in a terminal, record it, commit it, or send its values in chat. The key configured in the managed cloud is not included in the GitHub download.

Set `AI_PROVIDER=gemini`, a model available to your account in `AI_MODEL`, and your key in `AI_API_KEY`. Keep `PUBLIC_URL=http://localhost:8000` for the controlled local demo. Preserve generated database/admin/signing credentials. Set `PAPERFLOW_CONFERENCE_ID=real-lncs`.

Open n8n, create/sign into its local owner account, then save that account's email/password as `N8N_OWNER_EMAIL` and `N8N_OWNER_PASSWORD` in `.env`. Quote a password containing special characters. The runner binds and activates the five existing workflow exports automatically.

Apply changed container settings:

```sh
docker compose up -d --force-recreate api worker dashboard
```

Open Dashboard > Setup and connectivity > Verify Gemini connection. Proceed only after the actual request says Connected. Configured alone is not a successful request. If the provider fails, fix account/model/quota/network access to `generativelanguage.googleapis.com` before claiming AI review. Keep all messages confined to local Mailpit; Compose enforces the DEMO SMTP route.

## 3. Supply genuine manuscripts and verified metadata

Follow the full manifest example in [REAL_DEMO.md](REAL_DEMO.md). Put five authorized actual sources and an actual author-corrected revision in the ignored `real-papers/` directory. The runner requires both DOCX and LaTeX, unique filenames, exactly five initial paper keys, provenance, and verified title/authors/affiliation/email/abstract/keywords for each paper. LaTeX ZIPs must include their required bibliography and assets. The metadata manifest belongs in `real-papers/manifest.json`.

Provide `revision.paper_key` and `revision.path` for the controlled test author. The runner waits for an actual reminder and submits that corrected file through the signed author portal. If other papers have blocking defects, their authors must also submit corrected files before final publication can complete; the runner automatically simulates only the designated revision.

For the late-document AI test, use an authorized test copy of a genuine long paper, place a deliberate language issue after extracted character 40000, and set `tail_issue.paper_key` and `tail_issue.evidence` to the expected exact source quote. Disclose the controlled defect and retain the unmodified source. The runner must actually observe a Gemini finding at that location; a deterministic-only finding does not satisfy this test.

Validate the private JSON without displaying its contents:

```sh
.verify-venv/bin/python -m json.tool real-papers/manifest.json > /dev/null
```

## 4. Configure the conference once

In Dashboard > Create a real-paper conference batch, use ID `real-lncs`. Preserve the supplied source-attributed LNCS profile and required conference name/coordinator fields. Configure expected paper keys `paper-1` through `paper-5`, `enabled=true`, `real_paper_mode=true`, `require_ai=true`, `demo_mode=true`, and `notifications_enabled=true`. Keep `publication_authorized=false`, `acknowledged_manual_checks=[]`, and `check_decisions={}` initially. Use `deadline_seconds=1800` and `reminder_seconds=[120,300]` for 2/5-minute reminders and a 30-minute deadline.

Do not upload through the dashboard before starting the runner; it performs the single initial bulk upload. Do not call lifecycle endpoints manually between stages.

Unsupported checks require actual individual editorial inspection and a recorded rationale. For a complete final-release test, the private manifest must contain the coordinator's explicit authorization:

```json
"final_authorization": {
  "authorized": true,
  "coordinator": "ACTUAL COORDINATOR IDENTITY",
  "reason": "Actual authorization for this controlled local demonstration package.",
  "check_decisions": {
    "EXACT CHECK NAME ACTUALLY REVIEWED": "Specific rationale based on actual inspection."
  }
}
```

Replace these examples with real decisions; do not blanket-acknowledge uninspected properties. Without this object the runner does not exercise final release. Authorization does not override blocking manuscript errors. Additional unsupported checks can be resolved through the authenticated coordinator policy editor, with matching names in `acknowledged_manual_checks` and rationales in `check_decisions`.

## 5. Record and run

Use OBS Studio or your preferred local recorder. Select the browser/terminal display, 1080p at 30 fps, and record to MKV (remux to MP4 afterward if needed). Close private configuration and credential dialogs before recording. Open Dashboard, n8n and Mailpit tabs.

Start recording, show successful setup and an empty selected conference batch, then run in the repository's WSL terminal:

```sh
PYTHONPATH=. .verify-venv/bin/python scripts/verify_real_demo.py \
  --conference real-lncs \
  --manifest ./real-papers/manifest.json \
  --restart-compose --timeout 3600 \
  --report ./data/real-verification/report.json
```

The runner activates the workflows, uploads the five sources, observes real calls/delivery, submits the designated author's supplied revision after its reminder, inspects outputs, and restarts API/worker/n8n after a successful authorized final assembly to check idempotency. Do not submit that same revision manually while the runner is doing it.

Record these actual events, allowing processing time:

1. Five active n8n workflows and successful execution details.
2. Five distinct paper IDs, independent statuses and rendered documents.
3. Paper-specific findings, rule provenance, full-document coverage, Gemini invocation evidence, and the deliberate late issue.
4. Mailpit correction messages, actual PDF attachments, deadlines and signed revision links.
5. The real timed reminder and its timestamp.
6. Version 2 of the designated paper, comparison of resolved/remaining/new findings, and cancellation of reminders for the old version.
7. A regenerated draft containing only eligible current versions, with pending papers excluded.
8. Final authorized PDF/DOCX books, proceedings and source/report archive once every selected paper is eligible.
9. The runner's restart check and final PASS/FAIL/NOT TESTED report.

Use Refresh conference status to observe updates. Explain that the controlled author response is supplied by the runner; document validation and SMTP delivery are real. Record failures honestly instead of presenting active containers or regression fixtures as a completed manuscript workflow.

## 6. Inspect and retain evidence

The runner writes `data/real-verification/report.json` and downloaded outputs under `data/real-verification/outputs/`. Server-generated publications are in `data/publications/<publication-id>/`. Open the book PDF and DOCX, DOCX-rendered PDF, `pagination.json`, metadata CSV, proceedings and final publication ZIP. Check real titles, author order, affiliations, abstracts, contents page numbers and author-index references.

A fully successful acceptance report has `complete=true` and every criterion PASS. Missing authorization, provider failures, absent findings or incomplete author corrections remain failures/unverified criteria. Share manuscript-containing recordings and evidence only with authorized viewers.

Stop recording after showing the report and opening the outputs. To stop services without deleting stored evidence:

```sh
docker compose down
```

Do not use `down -v` unless intentionally deleting database state. If a page refuses connections, inspect `docker compose ps` and private logs with `docker compose logs --tail=80 api dashboard worker n8n`. This local deployment uses ports 8501/8000/5678/8025; earlier cloud-only port numbers do not apply.
