# Stage status matrix

## Stage 17 authority matrix

This matrix is the Stage 17 authority view. PostgreSQL is the project's only
database. Legacy fixture results are historical compatibility evidence only;
current database evidence uses local isolated PostgreSQL schemas. Neither is
deployment, production capacity, SLA, real-device, or production database evidence.

| Stage | Name | Status | Implemented scope | Verified scope | Deferred scope | Blocked scope | Evidence files | Database evidence | App evidence | Production boundary | Next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0-10 | Platform baseline | COMPLETE_WITH_HISTORICAL_BOUNDARIES | Core platform and historical migrations | Historical reports only | Advanced video and production operations | None | `backend/db/stage10*-*.json` | Historical database audits | Historical | Not deployed | Stage 18 authorization |
| B-R2 | Activity delete | COMPLETE | Soft delete and reference detachment | Local isolated PG | Hard delete | None | `backend/tests/activity_delete_postgres.py` | Isolated PG | N/A | No production delete proof | Review with Stage 18 |
| 11A | Sync architecture | COMPLETE | Contracts and migration design | Static/config evidence | Provider delivery | None | `backend/tests/message_sync_config.py` | N/A | N/A | Design is not deployment | Maintain contracts |
| 11B | Device sync | COMPLETE | Device, sync, checkpoint, reconcile | Local isolated PG | Cross-instance transport | None | `backend/tests/message_sync_postgres.py` | Isolated PG | `app/api/messageSync.ts` | REST remains authority | Broker authorization |
| 11C | Fake Push | COMPLETE_WITH_SINGLE_CHANNEL_SCOPE | Fake token/delivery lifecycle | Local isolated PG | APNs/FCM and real devices | None | `backend/tests/stage11c_postgres.py` | Isolated PG | Sync bridge only | Test-only `channel='push'` | Real provider authorization |
| 11D | Realtime wake-up | COMPLETE_SINGLE_INSTANCE_BASELINE | Authenticated process-local WebSocket | Local isolated PG/controlled clients | Broker fan-out | None | `backend/tests/stage11d_realtime_api.py` | Isolated PG | `app/api/messageRealtime.ts` | No multi-instance support | Broker authorization |
| 12A | Message editing | COMPLETE_WITH_BOUNDARIES | Sender text edits | Local isolated PG | Rich edits | None | `backend/tests/stage12_messages_api.py` | Isolated PG | API client | No production validation | Stage 18 validation |
| 12B | Reactions | COMPLETE_WITH_BOUNDARIES | One reaction/user/message | Local isolated PG | Expanded reactions UI | None | `backend/tests/stage12_messages_api.py` | Isolated PG | API client | No production validation | Stage 18 validation |
| 12C | Forwarding | COMPLETE_WITH_BOUNDARIES | Safe text/object forwarding | Local isolated PG | Media/Analysis forwarding | None | `backend/tests/stage13cd_forward_api.py` | Isolated PG | API client | No production validation | Stage 18 validation |
| 12D | Basic groups | COMPLETE_WITH_BOUNDARIES | Roles and member lifecycle | Local isolated PG | Advanced governance | None | `backend/tests/stage12_messages_api.py` | Isolated PG | API client | No production validation | Stage 18 validation |
| 12-M | Historical import compatibility | COMPLETE_WITH_BOUNDARIES | Additive legacy upgrade | Historical fixture | Runtime migration | None | `POSTGRES_MIGRATION_GUIDE.md` | Historical only | N/A | Not a runtime database path | Authorized import |
| 12-PG | PostgreSQL proof | COMPLETE_WITH_BOUNDARIES | Additive isolated upgrade | Local isolated PG | Public/production migration | None | `backend/tests/stage12_migration_postgres.py` | Isolated PG only | N/A | Not production validated | Authorized migration |
| 13A | Object access | COMPLETE_WITH_BOUNDARIES | Permission adapters/reference envelope | Local isolated PG | More object types | None | `backend/tests/stage13a_business_object_cards.py` | Isolated PG | N/A | Read-time authorization only | Expand only if approved |
| 13B | Object cards | COMPLETE_WITH_BOUNDARIES | Client card states | Static regression | Full object workflows | None | `app/tests/message_business_object_card_static.py` | N/A | Static app evidence | Not a UX release proof | UI authorization |
| 13C-D | Object forwarding/lifecycle | COMPLETE_WITH_BOUNDARIES | Safe forwarding and rehydration | Local isolated PG | Analysis/media transfer | None | `backend/tests/stage13cd_forward_api.py` | Isolated PG | API client | No production validation | Stage 18 validation |
| 14A | Search | COMPLETE_WITH_BOUNDARIES | Authorized filtered search | Local isolated PG | FTS/ranking | None | `backend/tests/stage14a_search_api.py` | Isolated PG | API types | No search cluster | FTS authorization |
| 14B | Moderation | COMPLETE_WITH_BOUNDARIES | Reports, review, audit | Local isolated PG | Appeals/full console | None | `backend/tests/stage14b_moderation_api.py` | Isolated PG | API types | No compliance certification | Policy approval |
| 14C | Notifications/metrics | COMPLETE_WITH_BOUNDARIES | Preferences, metrics, AI status | Historical regression evidence | AI execution | None | `backend/tests/message_notification_preferences_api.py` | Legacy fixture evidence | API types | No AI review | PostgreSQL validation |
| 14D-MVP | Governance requests | COMPLETE_WITH_BOUNDARIES | Export/deletion orchestration | Service/static evidence | Legal retention/hard delete | None | `backend/app/compliance/` | Legacy fixture evidence | N/A | No certified compliance | PostgreSQL validation |
| 14D-F | Export/WebSocket cleanup | COMPLETE_WITH_BOUNDARIES | Protected test storage/user cleanup | Local isolated PG | Production storage/multi-instance | None | `backend/tests/stage14df_export_websocket.py` | Isolated PG | N/A | Test provider only | Provider authorization |
| 15 | Release audit | RELEASE_CANDIDATE_AUDITED_WITH_BOUNDARIES | Regression/audit preparation | Historical audit evidence | Deploy/traffic validation | None | Stage 15 audit records | Isolated evidence only | TypeScript check | Not released | Stage 18 authorization |
| 16A | PostgreSQL baseline | COMPLETE_WITH_BOUNDARIES | Isolated schema/dependency gate | Local isolated PG | Production migration | Environment-dependent | `docs/messages/STAGE16A_POSTGRES_BASELINE.md` | Isolated PG only | N/A | No production DB proof | Authorized production validation |
| 16B | Dependency adapters | COMPLETE_WITH_BOUNDARIES | Test storage/realtime interfaces | Historical contract regression | Object store/broker | None | `backend/tests/stage16b_adapters.py` | Legacy fixture evidence | Realtime bridge | Single process/test storage | PostgreSQL/provider validation |

| Stage | Status | Implemented / verified scope | Deferred / blocked | Evidence |
|---|---|---|---|---|
| 0-10 | COMPLETE_WITH_HISTORICAL_BOUNDARIES | Core tennis platform, CV, uploads, migrations and release audits recorded in historical evidence | Production capacity, advanced video and external dependencies | `backend/db/stage10*-*.json` (ignored historical evidence) |
| B-R2 | COMPLETE | Activity soft-delete and reference detachment | Hard delete | `backend/db/b-r2-activity-delete-report-20260830-135547.json` |
| 11A | COMPLETE | Realtime/Push architecture baseline | Provider delivery | `backend/tests/message_sync_config.py` |
| 11B | COMPLETE | Device sync, cursor, checkpoint and reconciliation | Multi-instance transport | `backend/tests/message_sync_api.py`, `backend/tests/message_sync_postgres.py` |
| 11C | COMPLETE_WITH_SINGLE_CHANNEL_SCOPE | Fake Push token/delivery lifecycle | APNs/FCM and real devices | `backend/tests/message_push_contract.py`, `backend/tests/stage11c_postgres.py` |
| 11D | COMPLETE_SINGLE_INSTANCE_BASELINE | Authenticated WebSocket wake-up | Broker fan-out | `backend/tests/stage11d_realtime_api.py` |
| 12A-D | COMPLETE_WITH_BOUNDARIES | Message operations, reactions, forwards and basic groups | Advanced governance/UI | `backend/tests/stage12_messages_api.py` |
| 12-M | COMPLETE_WITH_BOUNDARIES | Historical additive import compatibility | Production import approval | `POSTGRES_MIGRATION_GUIDE.md` |
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
