The repairs are implemented in the current working tree. The real five-manuscript acceptance run is **incomplete**.

| Criterion | Status | Evidence / dependency |
|---|---|---|
| Suite A regression | PASS | 29 tests; 0 failures/errors; actual local PostgreSQL, LibreOffice, isolated TeX and Mailpit transport exercised |
| Runtime infrastructure | PASS | Actual readiness probes; 5 active n8n workflows and 20 recent successful idle executions. Compiler network disabled/read-only, no Docker socket. These are not manuscript acceptance events. |
| Actual Gemini connectivity | FAIL | Key available: True; ProxyError; active policy does not allow generativelanguage.googleapis.com |
| One bulk upload of five genuine sources | NOT TESTED | Five real manuscripts, metadata and a real corrected version have not been supplied; Gemini is blocked by network policy |
| Independent ingestion, segregation, verified metadata and rendering | NOT TESTED | Five real manuscripts, metadata and a real corrected version have not been supplied; Gemini is blocked by network policy |
| Official-template checks and full-document Gemini review | NOT TESTED | Five real manuscripts, metadata and a real corrected version have not been supplied; Gemini is blocked by network policy |
| Real paper-specific correction PDFs | NOT TESTED | Five real manuscripts, metadata and a real corrected version have not been supplied; Gemini is blocked by network policy |
| SMTP correction receipt and attachment integrity for real papers | NOT TESTED | Five real manuscripts, metadata and a real corrected version have not been supplied; Gemini is blocked by network policy |
| n8n scheduled reminder for real paper | NOT TESTED | Five real manuscripts, metadata and a real corrected version have not been supplied; Gemini is blocked by network policy |
| Author portal receives actual corrected paper | NOT TESTED | Five real manuscripts, metadata and a real corrected version have not been supplied; Gemini is blocked by network policy |
| Automatic revalidation and resolved/remaining/new comparisons | NOT TESTED | Five real manuscripts, metadata and a real corrected version have not been supplied; Gemini is blocked by network policy |
| Draft regenerates from newly eligible current versions | NOT TESTED | Five real manuscripts, metadata and a real corrected version have not been supplied; Gemini is blocked by network policy |
| Final authorized PDF/DOCX, proceedings and archive generation | NOT TESTED | Five real manuscripts, metadata and a real corrected version have not been supplied; Gemini is blocked by network policy |
| Real output metadata, contents, author index and hashes inspected | NOT TESTED | Five real manuscripts, metadata and a real corrected version have not been supplied; Gemini is blocked by network policy |
| Service restart with no duplicate papers, mail or reminders | NOT TESTED | Five real manuscripts, metadata and a real corrected version have not been supplied; Gemini is blocked by network policy |

The generated books listed below are clearly labelled Suite A fixture outputs. They test rendering and page references; they are not real conference proceedings.

- `data/publications/24da00c8b8f846ebbcce6f9d02e7332b/draft-package.zip` (local fixture file, excluded from Git) — SHA256 `27e2a4b995ffdffffb9cf3add9a51507314b3b115fb600533663f4c6f3597963`
- `data/publications/24da00c8b8f846ebbcce6f9d02e7332b/9d7d87131e64455caaf5e7855b8d0792.pdf` (local fixture file, excluded from Git) — SHA256 `b96b384c31d5931668c5f21869ece29ce353b2dca45f435f48d5c9572cab750d`
- `data/publications/24da00c8b8f846ebbcce6f9d02e7332b/book-of-abstracts.html` (local fixture file, excluded from Git) — SHA256 `2707d4f486f1697808108d9a2ca917d963c3c21035919c1d9060811e668048c0`
- `data/publications/24da00c8b8f846ebbcce6f9d02e7332b/audit.json` (local fixture file, excluded from Git) — SHA256 `0a8041312d6284e204deee338b9d18fe95cbd0e53b7988bff5fad563ef364580`
- `data/publications/24da00c8b8f846ebbcce6f9d02e7332b/metadata.csv` (local fixture file, excluded from Git) — SHA256 `00e6cc3324af9e89db634908d643ce8ec0e0bb12411324be4dc2b5724ff162e0`
- `data/publications/24da00c8b8f846ebbcce6f9d02e7332b/camera-ready-sources.zip` (local fixture file, excluded from Git) — SHA256 `38ce665014944c1ceaa078c4da9e2d99f8e27b16f0af457a9525fecc4c3abaf3`
- `data/publications/24da00c8b8f846ebbcce6f9d02e7332b/book-of-abstracts.pdf` (local fixture file, excluded from Git) — SHA256 `f589f2b8c537691a31f36a13576c185e1e4cf24d9dc76a890d02560a425154e0`
- `data/publications/24da00c8b8f846ebbcce6f9d02e7332b/book-of-abstracts-docx.pdf` (local fixture file, excluded from Git) — SHA256 `6e6e68e2022d83a00808c93fe28b5fe3a8ef9e7855846884c82a42396c4b780c`
- `data/publications/24da00c8b8f846ebbcce6f9d02e7332b/book-of-abstracts.docx` (local fixture file, excluded from Git) — SHA256 `f51b605f4efd15f94ac79d4915b9fb50a8a94eb9ed9c2ed462c64d80d680613f`
- `data/publications/24da00c8b8f846ebbcce6f9d02e7332b/proceedings.pdf` (local fixture file, excluded from Git) — SHA256 `5d72cd216ee6555f6eff841ad3f44c5981f9f908cdc320035decbd2fe6171407`
- `data/publications/24da00c8b8f846ebbcce6f9d02e7332b/pagination.json` (local fixture file, excluded from Git) — SHA256 `821de5ccf9c6306d594801d340997763390fd7dda8c72ae93119686831945c64`

Startup and secure configuration: [REAL_DEMO.md](REAL_DEMO.md). Versioned workflow exports: [workflows](workflows). Runner: [scripts/verify_real_demo.py](scripts/verify_real_demo.py). Regression evidence: [verification/suite-a.xml](verification/suite-a.xml). Actual Gemini probe: [GEMINI_CONNECTION_STATUS.json](GEMINI_CONNECTION_STATUS.json). Runtime health/idle n8n execution evidence: [verification/runtime-status.json](verification/runtime-status.json).

Required next inputs: five genuine papers plus a corrected author revision and verified metadata; permit `generativelanguage.googleapis.com` in the active environment network settings. Keep the existing API key in secure settings. Unsupported checks and final release require the coordinator’s explicit recorded decisions. No real author email has been sent by this deployment; Compose confines SMTP to the internal Mailpit network.
