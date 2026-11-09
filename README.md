# PaperFlow AI — Autonomous Springer Conference Agent

Use [REAL_DEMO.md](REAL_DEMO.md) for the Windows/WSL2 real-paper setup and [DEMO_RECORDING.md](DEMO_RECORDING.md) for the recording walkthrough. Run `bash scripts/start_demo.sh` from a WSL terminal to create the local verification environment, generate private local configuration, start Docker Compose and retain the reviewed LNCS class.

The real-paper acceptance run is **incomplete**. The existing Gemini key is present in the cloud environment, but the provider request fails through its network proxy. Five real manuscripts have not been supplied. See [REAL_ACCEPTANCE_RESULTS.md](REAL_ACCEPTANCE_RESULTS.md) for the PASS/FAIL/NOT TESTED matrix and [verification](verification) for recorded regression and infrastructure evidence. Historical synthetic demonstrations are not real-paper acceptance evidence.

FastAPI performs document operations; five n8n schedules drive ingestion, review completion, reminders, revisions and publication. PostgreSQL stores lifecycle state; Redis/Celery runs validation jobs; Mailpit captures test messages locally. Gemini is mandatory in real-paper mode. LanguageTool is optional and its skipped/failed analysis is reported explicitly.

## Run locally with Docker

Requires Docker Desktop with WSL2 integration, Linux containers, Python 3 with venv, and Docker Compose v2. Read [REAL_DEMO.md](REAL_DEMO.md) before enabling the conference workflow.

```sh
bash scripts/start_demo.sh
```

A dedicated network-disabled compilation service handles LaTeX. Application workers do not mount the Docker socket. The compiler has a read-only root filesystem, resource limits and separate restricted identities for compilation jobs. No application credentials are passed to it.

Use http://localhost:8501 for the dashboard, http://localhost:8000/docs for the API, http://localhost:5678 for n8n, and http://localhost:8025 for Mailpit, after running Compose on your own PC. Bindings are loopback-only. Edit `.env` privately to set the Gemini key and existing n8n owner credentials. Never commit or screen-record the file. `PUBLIC_URL=http://localhost:8000` is appropriate for the local controlled demo; sharing author links beyond your PC requires a reachable protected API address.

Managed-cloud builds require the configured proxy and CA trust. Use the `proxy_ca` BuildKit secret as documented in [REAL_DEMO.md](REAL_DEMO.md); keep TLS verification enabled.

`data/`, local real-paper inputs and named PostgreSQL, Redis and n8n volumes are private persistent state. Back up the database and files together. `docker compose down` preserves named volumes; `down -v` erases them.

## Current cloud development instance

The prepared Python environment is `/workspace/paperflow-venv`. Shared development services use `compose.cloud.yaml` (Compose project `paperflow-dev`); application configuration is the ignored `.env` inside this checkout. Activate the virtual environment and run:

```sh
cd /workspace/AUTONOMOUS_REVIEWER.ai
. /workspace/paperflow-venv/bin/activate
python scripts/start_local.py
curl --fail http://127.0.0.1:8000/health
PYTHONPATH=. pytest -q
```

The helper starts the API, two-worker Celery process, and Streamlit, retaining logs and PIDs outside the checkout. It does not replace the Compose deployment. Stop only its recorded process groups when restarting. Existing cloud checkouts are already isolated; do not create Git worktrees for routine work.

## Working cycle

1. Upload DOCX, text PDF, TEX or ZIP projects. Optional CSV headers: `filename,title,authors,email,track,affiliation`; filenames match uploaded files. CSV metadata cannot bypass approval. Uploads are capped at 30 MiB, ZIPs at 1,000 members/100 MiB expanded. Duplicate originals return 409. Each batch file has its own outcome; one invalid file does not discard others.
2. Select IEEE, LNCS or CCIS. Configure official numeric requirements through the profile JSON editor, supplying a new version and authoritative source. Supported keys: `width_mm,height_mm,max_pages,tolerance_mm,top_mm,bottom_mm,left_mm,right_mm,columns`. Upload official templates with `POST /profiles/{name}/template`; they are retained as evidence, not automatically interpreted as requirements. Existing validation retains a profile snapshot; rerun to use a changed profile.
3. Inspect extracted text, DOCX section layout, PDF dimensions, repeated words, numeric citation gaps, structured findings, per-check coverage, and the rendered manuscript. Download PDF/HTML correction reports. Unverifiable properties are marked for review; no publisher certification is claimed.
4. Edit title, semicolon-separated authors, affiliations, email, and track. Prepare an author email, inspect it, approve it, and send. Local SMTP goes to Mailpit. Revision links expire after 14 days. They authorize only a new version for one paper. The original remains immutable; revisions invalidate publication approval and trigger revalidation. Version comparisons report resolved/new/persisting issue fingerprints.
5. Review all findings, skipped checks and abstract extraction before approving a current version. Publication requires explicit approval and metadata. Generate the abstract book (PDF/DOCX/HTML), consolidated proceedings, individual approved PDFs, source ZIP, metadata CSV and JSON compliance audit. Only current approved versions enter exports.

Safe correction currently normalizes DOCX nonbreaking spaces only. It preserves originals, records before/after changes, verifies text round-tripping and requeues validation; it never declares scientific or formatting issues fixed by assumption. Semantic edits remain author/editor work.

## Inspection boundaries

The profiles intentionally contain no invented IEEE/Springer numeric defaults. DOCX section margins/columns and rendered page dimensions/count can be checked when configured. Fonts/runs and paragraph style/spacing observations are extracted, but inherited fonts, publisher heading rules, figure quality, captions, affiliations, mathematical correctness, citation style, and reliable PDF column/margin inference still require human review. Scanned PDFs have no OCR and are flagged. Abstract extraction is heuristic and must be checked by the editor; source text is not rewritten. Complex publisher-specific packages may require extending the TeX image with official template dependencies. TeX runs with no network, no shell escape, read-only root, no capabilities, an unprivileged task identity where available, resource limits and a wall-clock timeout; project ZIP traversal and symlinks are rejected. Do not treat this development deployment as a hardened multitenant document service.

Optional environment settings:

- `AI_PROVIDER=openai|gemini`, `AI_MODEL`, `AI_API_KEY`: schema-validated suggestions with source evidence only, always human-reviewed. API costs/credentials are optional. Configuring a provider permits sending manuscript text to it; obtain the necessary confidentiality authorization first.
- `LANGUAGETOOL_URL`: trusted local LanguageTool HTTP service, queried via `/v2/check`. If absent, grammar coverage is explicitly skipped.
- `CROSSREF_ENABLED=true`: DOI-resolution requests to `api.crossref.org`; resolution does not prove bibliographic equivalence. Enable destination access in cloud settings when needed.

Missing optional services, provider errors and extraction uncertainty appear in check coverage. They are not reported as passes.

## Legacy manual workflow notes

The five current workflow exports have been replaced by the scheduled autonomous flows documented in AUTONOMOUS.md. The following describes the retained manual API compatibility layer.

### Manual API orchestration (target 1.123.0)

Five inactive importable exports live in `workflows/01-*.json` through `05-*.json`. Import each into n8n, set `PAPERFLOW_API_URL=http://api:8000`, and bind each HTTP Request node to an n8n Header Auth credential with header name `Authorization` and value `Bearer <your administrator token>`. No exported credential IDs or values are included. Keep webhooks and schedules inactive until ready. The owner setup for n8n remains yours.

POST webhook bodies use stable `event_id` values:

```json
{"event_id":"intake-batch-001","version_ids":["existing-version-id"]}
```

Intake receives IDs registered through the upload API; binaries never traverse n8n. Completion uses `{event_id,paper_id}` and creates an approval-pending correction email/report. Communication uses `{event_id,message_id}` and sends only previously editor-approved messages. Author revision uploads go directly to the signed API route and automatically queue validation. Reminders run daily and return overdue papers for editor escalation; further external contact needs approval. Assembly uses `{event_id,publication:{conference,paper_ids,confirm_editorial_approval:true}}` and refuses unapproved versions.

SMTP delivery runs in the API, orchestrated by n8n HTTP nodes, rather than an n8n SMTP node. This centralizes approval checks and delivery state. A message marked `Sending` or `Delivery uncertain` is never blindly retried; inspect SMTP before resolving it. Durable event IDs are stored in PostgreSQL. Reused IDs return the prior outcome; failed/uncertain events need investigation and a consciously chosen new event ID. This is not an exactly-once delivery guarantee. Scheduled reminder output is an editorial queue, not an automatic external reminder campaign.

The exports were structurally checked and imported into disposable n8n. The included manual three-event fixture tests accepted, duplicate and malformed events within one execution; API tests separately verify durable cross-request deduplication. Credential-bound production webhook execution is not claimed by these fixture checks.

## Tests and demo

```sh
PYTHONPATH=. pytest -q
python scripts/make_samples.py
python scripts/demo.py
```

The demo requires running local API/worker/PostgreSQL/Redis/Mailpit and the `paperflow-tex:local` image. Never point it at production SMTP. It generates ten mixed manuscripts (four DOCX, three PDFs, three TeX ZIPs) containing deliberate repeated-word issues, uploads/validates, downloads reports, proves pre-approval sending is denied, sends approved local emails, uploads genuinely corrected DOCX revisions, checks issue resolution and approval invalidation, approves and downloads publication exports. It then ingests 100 small, distinct PDFs through the actual API and Celery queue. Results are saved to `DEMO_RESULTS.json`; these synthetic timings are not large-manuscript performance guarantees. Tests use a development database and leave synthetic records for inspection. Use a disposable database for CI.

`schema.sql` documents SQLAlchemy's initial schema. Automatic `create_all` is for initial development setup, not a migration system. This repository is a working development implementation with the inspection and deployment limitations stated above; production readiness and complete publisher-rule coverage are not claimed.
