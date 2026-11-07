# Autonomous Springer conference agent

The default dashboard is now the autonomous conference view. The five n8n scheduled workflows decide when to inspect intake, process validation outcomes, send notifications/reminders, ingest revisions, and assemble a complete batch. FastAPI implements operations; Celery performs independent document jobs. No dashboard timer or Python lifecycle polling loop performs the agent actions.

## Template and acceptance policy

Use the official Springer LLNCS 2.22 class, redistributed in the signed Debian TeX Live publisher package. `Dockerfile.tex` installs `texlive-publishers`. After building it, run:

```sh
python scripts/retain_lncs_template.py
```

This retains the unmodified class and provenance in ignored `data/conference-template.zip`; `profiles/lncs-provenance.json` records its SHA256 and declared 122 mm × 193 mm text area. The body size is the loaded article class's 10pt default. No unverified conference page limit is invented. The direct publisher reference URL is recorded, but its host was blocked in the current cloud policy; the class was obtained through the signed package repository instead. The archive is reproducible from the TeX image.

`profiles/conference-demo.json` contains only these supported class-derived rules. DOCX section textblock dimensions and effective body font sizes are compared. LaTeX uses the `llncs` class in a restricted container, runs two passes, records compiler textblock dimensions, and flags unresolved references/warnings. Page sizes/count, DOCX fonts/styles/section geometry, abstract/keyword extraction, repeated words, citations and optional grammar/AI results remain evidence in reports. Complex headings/captions/figure quality, DOCX style equivalence and scientific correctness need a single final editorial review; they are never labelled publisher-certified.

Production configuration requires a retained official template and defaults to requiring a configured AI provider. AI keys belong in secure environment settings (`AI_PROVIDER`, `AI_MODEL`, `AI_API_KEY`), never submission metadata. A demo may explicitly disable the AI prerequisite, in which case the evidence says skipped. The deterministic repeated-word test is not presented as AI analysis.

## Configure once, then enable

Start the existing API/worker/shared services (README), or use Docker Compose. Apply `PUT /agent/conferences/{id}` with an admin bearer token and a JSON policy. Example fields:

```json
{
  "name": "Conference LNCS Proceedings",
  "expected_papers": ["paper-1","paper-2","paper-3","paper-4","paper-5"],
  "coordinator_email": "coordinator@example.test",
  "notifications_enabled": true,
  "publication_authorized": false,
  "enabled": true,
  "demo_mode": false,
  "deadline_seconds": 604800,
  "reminder_seconds": [172800,432000],
  "max_versions": 4,
  "require_ai": true,
  "acknowledged_manual_checks": [],
  "profile": {"name":"Springer LNCS class 2.22","version":"llncs-2.22","source":"https://resource-cms.springernature.com/springer-cms/rest/v1/content/19238648/data/v8","requirements":{"text_width_mm":122,"text_height_mm":193,"font_size_pt":10,"columns":1,"tolerance_mm":1}}
}
```

Set `PAPERFLOW_CONFERENCE_ID` on the n8n service. Import the five `workflows/0*.json` exports, bind each HTTP node to the same Header Auth credential (`Authorization: Bearer <administrator token>`), then activate the schedules once. Exports are intentionally inactive and contain no credentials. Target runtime: n8n 1.123.0. Current checks run every five seconds; for a production conference, adjust the five Schedule Triggers to a suitable minute interval. Production reminder offsets are day-based; accelerated offsets are permitted only in demo mode.

`notifications_enabled` is the coordinator's authorization for routine correction mail, revision updates, scheduled reminders and escalations to the configured recipients. It does not imply publication authorization. `publication_authorized` can be enabled once for the batch or at the single final gate. Unsupported-check acknowledgments are explicit policy entries; unresolved critical metadata blocks only the affected submission. Do not enable public sending with a test recipient policy or an unreviewed SMTP destination.

## Folder source contract

Watch folder: `data/conferences/{id}/inbox/`. Folder ingestion is the implemented source; email inbox polling is an alternative source not required to run this folder-based deployment.

For bare new files, use an expected batch key as the filename, e.g. `paper-1.docx`. The detector waits for two seconds of stable file modification time, snapshots it into a ready bundle, and extracts labelled metadata. DOCX Title style is accepted for title; `Authors:`, `Affiliation:` and `Email:` paragraphs are recognized. LaTeX `title`, `author`, `institute` and a unique source email are supported conservatively. Ambiguity is recorded, never guessed.

For paired sources/PDFs, metadata, or revisions, write a bundle directory:

```
inbox/event-001/
  paper.docx              # or paper.zip / main.tex
  accompanying.pdf        # optional; retained as an attachment, never trusted instead of source rendering
  submission.json         # atomically renamed into place AFTER sources are complete
```

```json
{"paper_key":"paper-1","source":"paper.docx","metadata":{"title":"Study","authors":"Author A; Author B","affiliation":"University","email":"author@example.test","track":"Main"}}
```

Conflicting source/sidecar metadata produces an exception or author request; a missing/unusable author address goes only to the exception queue. Paths, sizes, symlinks, ZIP traversal and archive expansion are validated. Source records and attachments are stored under `data/papers/{paper_id}/{version}/`. Each file has an independent receipt and validation outcome. Repeated identical bundles have no second effect; changed invalid manifests can be corrected and detected as new events.

## Revision and reminder lifecycle

Correction messages contain a paper-specific signed upload URL and UTC deadline. Authors may use the portal, or place another source bundle with the original `paper_key` and `revision_token` from that signed URL. A bare filename or claimed paper ID cannot authorize a revision. n8n matches tokens, saves versions, queues revalidation and compares resolved/new/remaining issue fingerprints. Valid portal revisions stop reminders immediately at the version check, even before validation completes. Corrupt/rejected uploads do not stop the existing deadline.

Reminders are sent after configured offsets from actual correction delivery; escalation uses the submission deadline. Durable keys `(conference,paper,version,kind)` prevent duplicate correction/reminder sends across schedule runs and restarts. Once overdue, the coordinator receives an escalation and the author stops receiving reminders. Configurable maximum source versions prevents indefinite correction cycles. Safe DOCX nonbreaking-space normalization uses the existing original-preserving correction function, records differences and reruns validation; no research claims are changed.

Dispatch state is persisted before SMTP. If a process crashes during delivery, `Sending` or `Delivery uncertain` requires coordinator investigation; it is never automatically resent. This is an intentional exception, not a promise of exactly-once SMTP delivery. API stage calls wait on a conference advisory lock with a 20-second bound, avoiding starvation when schedules fire together; failed calls use bounded n8n retries. API failures have bounded n8n retries. Queue submissions are recoverable on subsequent intake/revision checks. Database uniqueness and retained receipt/message keys enforce durable idempotency.

## Completion and final gate

No blocking issues → provisional `Publication Ready`. Missing required AI analysis, ambiguous source metadata, unavailable rendering, correction-round exhaustion and exceptional failures remain visible. Unsupported checks are collected at the final batch gate. All configured paper keys must be present and ready before assembly. Publication additionally requires explicit coordinator authorization and acknowledged unsupported checks.

The agent then generates the Book of Abstracts (PDF, DOCX, HTML), consolidated proceedings, individual PDFs, original approved sources, metadata CSV, compliance audit, and a complete ZIP containing outputs and per-paper PDF/HTML reports. Source metadata and abstracts are used without rewriting claims. The coordinator receives a real email when ready. Assembly intent is persisted before output generation; an interrupted assembly is marked uncertain and requires inspection instead of silently producing duplicate packages.

## Real five-paper rehearsal

```sh
. /workspace/paperflow-venv/bin/activate
python scripts/retain_lncs_template.py
python scripts/run_agent_demo.py
```

Prerequisites: native API dependencies, local PostgreSQL/Redis/Mailpit, running Celery worker, `paperflow-tex:local`, Docker and free loopback test ports 15679/18080. The script uses a disposable n8n owner/database, imports and saves the five actual workflows, binds a temporary local API credential, and activates the schedules through n8n's owner API. It never triggers lifecycle endpoints itself. It places initial sources and simulates only author revision actions while observing GET status responses. The coordinator policy is explicitly enabled for this controlled test. Reminders really wait two minutes; no fake application clock or backdated send records are used.

The five cases are: an initially passing DOCX, wrong DOCX textblock/body font, broken LNCS compilation/reference, repeated-word plus missing affiliation, and a repeated-word case whose author waits for a real reminder. Authors 2–4 revise through watched bundles; author 5 responds after the timed reminder. The demo verifies Mailpit message contents/IDs, issue resolution, version advancement, ready states, generated files and downloads. It records status snapshots, timestamps, API/n8n logs and received email bodies in ignored `data/agent-runs/{run}/`, with a shareable summary in `AGENT_DEMO_RESULTS.json`. Temporary plaintext n8n credential exports are deleted on completion; never commit run directories or n8n database files.

Use `PYTHONPATH=. pytest -q` for integration/safety tests. The old manual-mode demonstration remains available separately but does not establish the autonomous acceptance criteria. No environment publication or Git push is performed by this demonstration.

For an authenticated production email relay, configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and either `SMTP_STARTTLS=true` or `SMTP_SSL=true`. TLS uses the system certificate store with verification enabled. Mailpit needs neither credentials nor TLS. Network grants for an external SMTP endpoint must be configured separately; credentials are never stored in workflow exports.
