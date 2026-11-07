# Autonomous Springer agent validation

Final recorded run: `agent-771bdecb`. See AGENT_DEMO_RESULTS.json and AUTONOMOUS.md.

- Full regression suite: 14 tests passed, including stable source detection, durable intake/message idempotency, unsafe path rejection, notification policy gating, concurrent schedule fairness, original-preserving safe correction, real two-pass LNCS rendering/geometry, secure portal handoff, reminder cancellation, SMTP delivery to local Mailpit, and the retained document/publication tests.
- Five actively scheduled n8n 1.123.0 workflows completed the lifecycle without manual lifecycle endpoint calls. All five have successful persisted executions and no execution errors in the final run. Initial implementation issues with CLI version history, REST readiness, local service routing and schedule-lock starvation were diagnosed and corrected before the successful run.
- Initial cases: Paper 1 publication-ready; Paper 2 had actual DOCX font/textblock errors; Paper 3 failed actual LaTeX compilation; Paper 4 had repeated-word and missing-affiliation findings; Paper 5 had a repeated-word finding and awaited a timed reminder.
- Four correction emails, one real two-minute reminder, and one coordinator publication notice were received by Mailpit (6 matched SMTP message IDs). Authors 2–4 revised through watched folders; author 5 used the signed portal. Revisions were revalidated and compared, all five reached publication-ready, and no later reminder was sent.
- Total final workflow time: 150.95 seconds. Book PDF: 8 pages. Consolidated proceedings: 5 pages. PDF/DOCX/HTML book, five individual PDFs, source ZIP, metadata CSV, audit, and complete publication ZIP were downloaded and checksummed.
- Official LLNCS 2.22 class retained from the signed Debian TeX Live publisher package. Its declared 122 mm × 193 mm textblock was checked against actual compilation. Direct publisher-package download remained policy-blocked; no network or verification bypass was used.
- Autonomous Streamlit dashboard rendered through its UI test harness with no exceptions. Updated application/TeX images built; isolated Compose startup, API/PostgreSQL health, autonomous endpoints and dashboard health checks passed.
- AI/provider credentials were absent. This controlled demo explicitly disabled the production AI prerequisite and records AI proofreading as skipped. No AI-backed linguistic accuracy or external SMTP/TLS delivery is claimed. Production defaults require configured AI analysis and the final unsupported-check/authorization gate.

Detailed status snapshots, API/n8n logs, received email contents, source/revision fixtures, audit events and generated outputs are retained at `/workspace/AUTONOMOUS_REVIEWER.ai/data/agent-runs/agent-771bdecb` (ignored, not for committing). Temporary plaintext credential exports were removed. Environment publication and Git push were not performed.

---

## Earlier manual development validation (historical)

# Executed validation

- Python dependency consistency: `pip check` passed.
- PostgreSQL integration suite: 5 tests passed, covering authentication, upload persistence, duplicate/format rejection, ZIP traversal rejection, real DOCX parsing, detected writing findings, report generation, approval gating, publication exports, secure revisions, approval invalidation, and durable automation deduplication.
- Actual API + Celery run: 10 mixed-format manuscripts completed validation (4 DOCX, 3 PDF, 3 LaTeX ZIP); intentional repeated-word findings detected. Ten PDF reports downloaded, ten approved emails received by local Mailpit, ten corrected revisions revalidated, then approved and included in downloaded abstract-book and proceedings exports. Total complete-cycle time: 22.01 seconds. See DEMO_RESULTS.json.
- Bulk: 100 small synthetic PDFs accepted, 100 completed, 0 rejected, 0 failed, 1.57 seconds with two Celery workers. This does not measure large or complex source projects.
- n8n 1.123.0: all five application exports and the three-event fixture imported in a disposable instance. Initial import failed due to missing versionId, corrected before successful retry. n8n emitted new-workflow webhook-removal warnings but then confirmed successful imports. Manual fixture actually produced accepted, duplicate and rejected results with successful node execution. Production credential-bound webhook and scheduled execution remain unverified.
- Docker: restricted TeX image and full application image built successfully with certificate/signature verification retained. Full Compose stack started on alternate loopback ports. Container API/worker smoke checks cover persistent DOCX upload, actual rendering, and correction PDF response; Streamlit health checked separately.
- OpenAI/Gemini, Crossref and optional LanguageTool service were not invoked. No provider credentials were supplied. These checks are reported skipped by default.

The app is a development implementation. Publisher-specific rules must be configured from official requirements; complex typography/semantics require human review. SMTP is orchestrated through the API, not a native n8n SMTP node; reminders produce an editorial escalation queue. See README for production hardening and other coverage limits.
