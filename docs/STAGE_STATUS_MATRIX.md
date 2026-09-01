# Stage status matrix

## Stage 17 authority matrix

This matrix is the Stage 17 authority view. Evidence labeled SQLite uses a
temporary test database; PostgreSQL evidence uses a local isolated schema only.
Neither is deployment, production capacity, SLA, real-device, or production
database evidence.

| Stage | Name | Status | Implemented scope | Verified scope | Deferred scope | Blocked scope | Evidence files | Database evidence | App evidence | Production boundary | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0-10 | Platform baseline | COMPLETE_WITH_HISTORICAL_BOUNDARIES | Core platform and historical migrations | Historical reports only | Advanced video and production operations | None | `backend/db/stage10*-*.json` | Historical SQLite/isolated PG | Historical | Not deployed | Stage 18 authorization |
| B-R2 | Activity delete | COMPLETE | Soft delete and reference detachment | Local API regression | Hard delete | None | `backend/tests/activity_delete_api.py` | Temporary SQLite | N/A | No production delete proof | Review with Stage 18 |
| 11A | Sync architecture | COMPLETE | Contracts and migration design | Static/config evidence | Provider delivery | None | `backend/tests/message_sync_config.py` | N/A | N/A | Design is not deployment | Maintain contracts |
| 11B | Device sync | COMPLETE | Device, sync, checkpoint, reconcile | SQLite and local isolated PG | Cross-instance transport | None | `backend/tests/message_sync_api.py` | Temporary SQLite; isolated PG | `app/api/messageSync.ts` | REST remains authority | Broker authorization |
| 11C | Fake Push | COMPLETE_WITH_SINGLE_CHANNEL_SCOPE | Fake token/delivery lifecycle | SQLite and local isolated PG | APNs/FCM and real devices | None | `backend/tests/stage11c_sqlite.py` | Temporary SQLite; isolated PG | Sync bridge only | Test-only `channel='push'` | Real provider authorization |
| 11D | Realtime wake-up | COMPLETE_SINGLE_INSTANCE_BASELINE | Authenticated process-local WebSocket | SQLite/local controlled clients | Broker fan-out | None | `backend/tests/stage11d_realtime_api.py` | Temporary SQLite | `app/api/messageRealtime.ts` | No multi-instance support | Broker authorization |
| 12A | Message editing | COMPLETE_WITH_BOUNDARIES | Sender text edits | SQLite regression | Rich edits | None | `backend/tests/stage12_messages_api.py` | Temporary SQLite | API client | No production migration | Stage 18 migration |
| 12B | Reactions | COMPLETE_WITH_BOUNDARIES | One reaction/user/message | SQLite regression | Expanded reactions UI | None | `backend/tests/stage12_messages_api.py` | Temporary SQLite | API client | No production migration | Stage 18 migration |
| 12C | Forwarding | COMPLETE_WITH_BOUNDARIES | Safe text/object forwarding | SQLite regression | Media/Analysis forwarding | None | `backend/tests/stage13cd_forward_api.py` | Temporary SQLite | API client | No production migration | Stage 18 migration |
| 12D | Basic groups | COMPLETE_WITH_BOUNDARIES | Roles and member lifecycle | SQLite regression | Advanced governance | None | `backend/tests/stage12_messages_api.py` | Temporary SQLite | API client | No production migration | Stage 18 migration |
| 12-M | SQLite upgrade | COMPLETE_WITH_BOUNDARIES | Additive legacy upgrade | Temporary SQLite | Default DB migration | None | `backend/tests/stage12_migration_sqlite.py` | Temporary SQLite | N/A | Default SQLite untouched | Authorized migration |
| 12-PG | PostgreSQL proof | COMPLETE_WITH_BOUNDARIES | Additive isolated upgrade | Local isolated PG | Public/production migration | None | `backend/tests/stage12_migration_postgres.py` | Isolated PG only | N/A | Not production validated | Authorized migration |
| 13A | Object access | COMPLETE_WITH_BOUNDARIES | Permission adapters/reference envelope | SQLite regression | More object types | None | `backend/tests/stage13a_business_object_cards.py` | Temporary SQLite | N/A | Read-time authorization only | Expand only if approved |
| 13B | Object cards | COMPLETE_WITH_BOUNDARIES | Client card states | Static regression | Full object workflows | None | `app/tests/message_business_object_card_static.py` | N/A | Static app evidence | Not a UX release proof | UI authorization |
| 13C-D | Object forwarding/lifecycle | COMPLETE_WITH_BOUNDARIES | Safe forwarding and rehydration | SQLite regression | Analysis/media transfer | None | `backend/tests/stage13cd_forward_api.py` | Temporary SQLite | API client | No production migration | Stage 18 migration |
| 14A | Search | COMPLETE_WITH_BOUNDARIES | Authorized filtered search | SQLite regression | FTS/ranking | None | `backend/tests/stage14a_search_api.py` | Temporary SQLite | API types | No search cluster | FTS authorization |
| 14B | Moderation | COMPLETE_WITH_BOUNDARIES | Reports, review, audit | SQLite regression | Appeals/full console | None | `backend/tests/stage14b_moderation_api.py` | Temporary SQLite | API types | No compliance certification | Policy approval |
| 14C | Notifications/metrics | COMPLETE_WITH_BOUNDARIES | Preferences, metrics, AI status | Existing regression evidence | AI execution | None | `backend/tests/message_notification_preferences_api.py` | Temporary SQLite evidence | API types | No AI review | AI authorization |
| 14D-MVP | Governance requests | COMPLETE_WITH_BOUNDARIES | Export/deletion orchestration | Service/static evidence | Legal retention/hard delete | None | `backend/app/compliance/` | Temporary SQLite evidence | N/A | No certified compliance | Policy approval |
| 14D-F | Export/WebSocket cleanup | COMPLETE_WITH_BOUNDARIES | Protected test storage/user cleanup | SQLite regression | Production storage/multi-instance | None | `backend/tests/stage14df_export_websocket.py` | Temporary SQLite | N/A | Test provider only | Provider authorization |
| 15 | Release audit | RELEASE_CANDIDATE_AUDITED_WITH_BOUNDARIES | Regression/audit preparation | Historical audit evidence | Deploy/traffic validation | None | Stage 15 audit records | Isolated evidence only | TypeScript check | Not released | Stage 18 authorization |
| 16A | PostgreSQL baseline | COMPLETE_WITH_BOUNDARIES | Isolated schema/dependency gate | Local isolated PG | Production migration | Environment-dependent | `docs/messages/STAGE16A_POSTGRES_BASELINE.md` | Isolated PG only | N/A | No production DB proof | Authorized production validation |
| 16B | Dependency adapters | COMPLETE_WITH_BOUNDARIES | Test storage/realtime interfaces | SQLite regression | Object store/broker | None | `backend/tests/stage16b_adapters.py` | Temporary SQLite | Realtime bridge | Single process/test storage | Provider/broker authorization |

| Stage | Status | Implemented / verified scope | Deferred / blocked | Evidence |
|---|---|---|---|---|
| 0-10 | COMPLETE_WITH_HISTORICAL_BOUNDARIES | Core tennis platform, CV, uploads, migrations and release audits recorded in historical evidence | Production capacity, advanced video and external dependencies | `backend/db/stage10*-*.json` (ignored historical evidence) |
| B-R2 | COMPLETE | Activity soft-delete and reference detachment | Hard delete | `backend/db/b-r2-activity-delete-report-20260830-135547.json` |
| 11A | COMPLETE | Realtime/Push architecture baseline | Provider delivery | `backend/tests/message_sync_config.py` |
| 11B | COMPLETE | Device sync, cursor, checkpoint and reconciliation | Multi-instance transport | `backend/tests/message_sync_api.py`, `backend/tests/message_sync_postgres.py` |
| 11C | COMPLETE_WITH_SINGLE_CHANNEL_SCOPE | Fake Push token/delivery lifecycle | APNs/FCM and real devices | `backend/tests/message_push_contract.py`, `backend/tests/stage11c_postgres.py` |
| 11D | COMPLETE_SINGLE_INSTANCE_BASELINE | Authenticated WebSocket wake-up | Broker fan-out | `backend/tests/stage11d_realtime_api.py` |
| 12A-D | COMPLETE_WITH_BOUNDARIES | Message operations, reactions, forwards and basic groups | Advanced governance/UI | `backend/tests/stage12_messages_api.py` |
| 12-M | COMPLETE_WITH_BOUNDARIES | Existing SQLite additive upgrade | Production migration | `backend/tests/stage12_migration_sqlite.py` |
| 12-PG | COMPLETE_WITH_BOUNDARIES | Isolated PostgreSQL legacy proof | Production migration approval | `backend/tests/stage12_migration_postgres.py` |
| 13A | COMPLETE_WITH_BOUNDARIES | Object access adapters and references | Full object UI | `backend/tests/stage13a_business_object_cards.py` |
| 13B | COMPLETE_WITH_BOUNDARIES | Unified object cards and client states | Full client workflow | `app/tests/message_business_object_card_static.py` |
| 13C-D | COMPLETE_WITH_BOUNDARIES | Secure forwarding and lifecycle hydration | Broader object types | `backend/tests/stage13cd_forward_api.py` |
| 14A | COMPLETE_WITH_BOUNDARIES | Authorized message/object/media search | FTS and advanced ranking | `backend/tests/stage14a_search_api.py` |
| 14B | COMPLETE_WITH_BOUNDARIES | Reports, moderation and audit | Appeals and AI enforcement | `backend/tests/stage14b_moderation_api.py` |
| 14C | COMPLETE_WITH_BOUNDARIES | Notifications, metrics and AI status contract | AI execution | `backend/tests/message_notification_preferences_api.py` |
| 14D-MVP | COMPLETE_WITH_BOUNDARIES | Export/deletion request orchestration and dry-run summaries | Hard delete/anonymization | `backend/app/compliance/` |
| 14D-F | COMPLETE_WITH_BOUNDARIES | Protected test-storage export and user WebSocket cleanup | Production storage/multi-instance | `backend/tests/stage14df_export_websocket.py` |
| 15 | RELEASE_CANDIDATE_AUDITED_WITH_BOUNDARIES | Unified release audit | Deployment and real traffic | Stage 15 audit response and regression scripts |
| 16A | COMPLETE_WITH_BOUNDARIES | Isolated PostgreSQL baseline and dependency gates | Production migration/dependencies | `docs/messages/STAGE16A_POSTGRES_BASELINE.md` |
| 16B | COMPLETE_WITH_BOUNDARIES | Storage and realtime adapter contracts | Real provider/broker | `backend/tests/stage16b_adapters.py`, `docs/messages/STAGE16B_DEPENDENCY_CONTRACTS.md` |

These statuses are repository evidence, not a production deployment claim.
