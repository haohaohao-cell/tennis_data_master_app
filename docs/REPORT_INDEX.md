# Report and evidence index

Stage 17 index generated on 2026-09-01. Timestamps below come from immutable
filenames when present; files without a timestamp are source/document evidence
rather than a generated test report. No report contents are copied here.

| Path pattern | Stages | Environment | Sensitivity / validity |
|---|---|---|---|
| `backend/db/stage10*-*.json` | 0-10 | Historical database audits | Generated and git-ignored; historical evidence, review before submission |
| `backend/db/stage11a-*.json` through `stage11d-*.json` | 11A-11D | Legacy fixtures and isolated PostgreSQL | Generated evidence; no credentials copied here |
| `backend/db/b-r2-activity-delete-report-*.json` | B-R2 | Local regression | Untracked generated evidence; inspect before submit |
| `backend/tests/*.py` stage/message scripts | 11-16B | Legacy temporary fixtures or caller-selected isolated PostgreSQL | Reproducible test sources; PostgreSQL evidence is authoritative |
| `docs/messages/STAGE14DF_BOUNDARIES.md` | 14D-F | Documentation | Current boundary statement |
| `docs/messages/STAGE16A_POSTGRES_BASELINE.md` | 16A | Isolated PostgreSQL | Current baseline, not production proof |
| `docs/messages/STAGE16B_DEPENDENCY_CONTRACTS.md` | 16B | Local/test contracts | Current dependency boundary |

| Evidence path | Stage | Generated time | Test scope | Environment | Sensitive data | Current validity | Historical-only |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `backend/db/b-r2-activity-delete-report-20260830-135547.json` | B-R2 | 2026-08-30 13:55:47 (filename) | Activity delete | Local regression | Review before staging | Current local evidence | No |
| `backend/db/stage11a-*.json`--`stage11d-*.json` | 11A-11D | Filename-derived | Sync, Fake Push, WebSocket | Legacy fixtures/isolated PostgreSQL | Not copied; review before staging | Historical audit evidence | Yes |
| `backend/tests/stage12_*.py` | 12 | Source timestamp not applicable | Operations and migrations | Legacy fixtures/isolated PostgreSQL | No known literal credential | Current reproducible source; PostgreSQL result is authoritative | No |
| `backend/tests/stage13*.py` | 13 | Source timestamp not applicable | Object cards and forwarding | Legacy temporary fixtures | No known literal credential | Historical compatibility source | No |
| `backend/tests/stage14*.py` | 14 | Source timestamp not applicable | Search, moderation, export cleanup | Legacy temporary fixtures | No known literal credential | Historical compatibility source | No |
| `backend/tests/stage16b_adapters.py` | 16B | Source timestamp not applicable | Adapter contracts | Legacy temporary fixture | No known literal credential | Historical compatibility source | No |

The index intentionally omits tokens, passwords, DSNs, storage keys, message
contents and absolute local paths. Historical JSON files remain untouched and
must be reviewed before any commit.
