# Windows / WSL2 real-paper verification

Use Docker Desktop with WSL2 integration and Linux containers. Run from the repository inside WSL2. No application container mounts the Docker socket. TeX compilation uses a separate network-disabled, read-only service; each job drops to its own non-root UID with private temporary storage and CPU/memory/process/time limits. Its controller has only the capabilities needed to change ownership, drop identities and terminate its children. It has no application credentials or manuscript-storage mount.

One-time setup:

```sh
python3 -m venv .verify-venv
. .verify-venv/bin/activate
python -m pip install -r requirements-verify.txt
python3 scripts/init_env.py
# Edit .env locally using an editor, not commands that print secrets.
# AI_PROVIDER=gemini, AI_MODEL=<model available to your key>, AI_API_KEY=<secure value>
# PAPERFLOW_CONFERENCE_ID=real-lncs
# MAIL_MODE=DEMO (Compose forces local Mailpit in this deployment)
docker compose up -d --build --wait
python3 scripts/retain_lncs_template.py
```

Create/sign into your local n8n owner account once in its UI. Set `N8N_OWNER_EMAIL` and `N8N_OWNER_PASSWORD` securely in the runner's local `.env`; the runner uses them only for initial workflow binding/activation and evidence reads. Do not commit the file. A local HTTP n8n owner session may require `N8N_SECURE_COOKIE=false` on a loopback-only development instance; use verified HTTPS and secure cookies for external deployment.

Use the dashboard's **Setup and connectivity** panel to verify a real Gemini request. The selected model is not considered connected merely because a key exists. The key is never read from a browser request or displayed in reports. Confirm your authorization to send unpublished manuscripts to Gemini before enabling analysis.

Create the `real-lncs` conference using **Create a real-paper conference batch**. Use the retained Springer profile and your actual conference name, expected paper keys, deadlines and coordinator address. Keep `real_paper_mode=true`, `require_ai=true`, `publication_authorized=false`, and `acknowledged_manual_checks=[]`. Accelerated 120/300-second reminders require `demo_mode=true`. This test flag does not mean that papers or service results are simulated. All mail is restricted to Mailpit; no SMTP authentication, TLS relay or external SMTP host is allowed in this configuration.

Place the **five actual source manuscripts** and an actual author-corrected revision in a private directory. The metadata JSON below describes the shape of each entry; repeat it for all five with real values. It is configuration, not a generated paper or abstract:

```json
{
  "papers": [
    {
      "paper_key": "paper-1",
      "path": "actual-manuscript.docx",
      "real_manuscript": true,
      "provenance": {"origin": "author submission; authorized controlled test"},
      "metadata_verified": true,
      "metadata": {
        "title": "<verified actual title>",
        "authors": "<verified author order; semicolon separated>",
        "affiliation": "<verified affiliation>",
        "email": "<verified corresponding author email>",
        "abstract": "<exact actual abstract>",
        "keywords": "<exact actual keyword line>"
      }
    }
  ],
  "revision": {"paper_key":"paper-5", "path":"actual-corrected-manuscript.docx"},
  "tail_issue": {"paper_key":"paper-4", "evidence":"<an intentionally introduced linguistic defect after character 40000>"}
}
```

Use five unique source filenames with DOCX and LaTeX represented. If the revision changes extracted metadata, provide its complete verified `metadata` object in the `revision` entry. The runner cannot infer that a paper is genuine: the submitter must declare its provenance and permission, and the supplied bytes/hashes are preserved. It does not substitute generated fixtures.

One-command verification after that setup:

```sh
PYTHONPATH=. python3 scripts/verify_real_demo.py --start \
  --conference real-lncs --manifest ./real-papers/manifest.json --restart-compose \
  --report ./data/real-verification/report.json
```

The runner starts Compose, makes a real Gemini connectivity request, binds/activates the five existing n8n flows, uploads the five actual files in one multipart request, and observes the backend. It does not call lifecycle stages manually. After a real reminder is received, it simulates the authorized author posting the supplied corrected manuscript through the token from the actual received message. It then checks version advancement, reminder cancellation, resolved findings, real Gemini chunk response IDs, complete coverage, actual n8n execution data for this conference, Mailpit message IDs and paper-specific error text, draft updates and output integrity. Final release is exercised only when the private manifest contains an explicit `final_authorization` object with `authorized: true`, the coordinator identity, a reason of at least 10 characters, and `check_decisions` mapping each individually inspected unsupported check to its rationale. It records these decisions through the authenticated conference configuration; it never invents or blanket-acknowledges them. Without this authorization, final publication remains NOT TESTED. With `--restart-compose`, it restarts the isolated test API, worker and n8n after final generation, observes fresh successful executions of all five workflows, and compares paper/version, message and publication identities for duplicates.

A complete result requires every acceptance criterion to pass. Missing manuscripts, credentials, a corrected version, designated tail issue, publication-eligible paper, service authorization or observed event results in a nonzero exit and a PASS/FAIL/NOT TESTED report. A Gemini transport error, invalid JSON, unsubstantiated evidence or failed chunk never becomes an AI-reviewed success. Successful chunks are cached privately and reused during recovery; summaries include character coverage and invocation IDs without manuscript bodies or credentials. Provider unit-test stubs are explicitly separate from real-demo evidence.

Drafts update when the set of current, metadata-verified eligible versions changes. They contain no placeholder abstracts. Contradictory or ambiguous metadata stays in the exception queue; use the explicit metadata-verification action before eligibility. The final publication still requires coordinator authorization and review of unsupported checks. Existing released packages are marked superseded rather than silently replaced after revisions.

Reports and generated drafts are under `data/real-verification/` and `data/publications/`; storage and credentials are ignored by Git. Per-chunk findings may contain confidential source evidence and remain in private storage; do not share it as a public CI artifact. Provider exception bodies and TeX source excerpts are not written to ordinary service logs.

```sh
PYTHONPATH=. pytest -q --tb=short
docker compose logs --tail=50 api worker compiler n8n  # inspect privately; never dump the environment
docker compose down  # preserves stored papers and named database volumes
```

The current checked-in `REAL_DEMO_VERIFICATION.json` is a failed preflight, not a successful real-paper demonstration. No five real manuscripts have been supplied. The configured Gemini key is present, but the actual provider request fails with ProxyError because the active cloud network policy blocks `generativelanguage.googleapis.com`; neither key validity nor model access has been verified. See `REAL_FIXES_VALIDATION.json` for the separately executed implementation tests and isolated compiler checks. Native Windows/WSL2 execution remains unverified until the runner is executed there.


The dashboard accepts multiple manuscripts without any metadata file; stable paper keys are allocated from the configured batch. An optional UTF-8 CSV can provide `filename,paper_key,title,authors,affiliation,email,abstract,keywords,track,metadata_verified`. Use quoted fields for commas/newlines. Set `metadata_verified=true` only after an actual coordinator check. Ambiguous metadata stays in an editorial exception; the system never fabricates missing authors or abstracts. JSON manifests remain supported by both dashboard and runner.

All nine editorial phases are recorded in `details.phase_history` and the audit table. `lifecycle_state` is shown on the dashboard; legacy scheduler states remain for backward compatibility. Failed/skipped Gemini analysis and undecided unsupported checks block real-paper draft eligibility. Enter individual decisions under `check_decisions` alongside their names in `acknowledged_manual_checks` using the coordinator policy editor.

PDF contents and index links resolve to actual rendered page numbers. DOCX PAGEREF fields are calculated by LibreOffice, checked against a separate rendered DOCX PDF, and retained for recalculation in Word. `pagination.json` records both formats' independently verified page maps; their pagination may differ. `book-of-abstracts-docx.pdf` is the DOCX rendering used for this verification. Final publication errors remain visible instead of creating a successful release record.

For Suite A inside the Compose stack, use:

```sh
docker compose exec -e AI_PROVIDER=disabled -e AI_API_KEY= -e GEMINI_API_KEY= -e GOOGLE_API_KEY= api python -m pytest -q --tb=short --junitxml=data/suite-a.xml
```

These regression tests use labelled fixtures and provider contract stubs where appropriate. They exercise actual LibreOffice, the isolated TeX service, PostgreSQL and local SMTP separately; they cannot establish five-real-paper acceptance or actual Gemini success. Run Suite B with the real manifest to establish those outcomes. Never treat historical `AGENT_DEMO_RESULTS.json` as current evidence.
