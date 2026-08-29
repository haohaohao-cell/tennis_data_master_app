import AsyncStorage from "@react-native-async-storage/async-storage";

import type { MessageCreateInput } from "@/api/messages";

const STORAGE_KEY = "tennis.message-outbox.v1";
const MEDIA_ATTEMPT_STORAGE_KEY = "tennis.message-media-attempts.v1";
const MAX_ITEMS = 100;
const TERMINAL_RETENTION_MS = 7 * 24 * 60 * 60 * 1000;

export type LocalSendState =
  | "queued"
  | "sending"
  | "sent"
  | "failed_retryable"
  | "failed_permanent"
  | "cancelled";

export type LocalMessageOutboxItem = {
  local_id: string;
  device_id: string;
  conversation_id: string;
  client_message_id: string;
  message: MessageCreateInput;
  draft_text: string;
  local_state: LocalSendState;
  attempt_count: number;
  next_retry_at: string | null;
  last_error_code: string | null;
  server_message_id: string | null;
  server_event_id: string | null;
  created_at: string;
  updated_at: string;
};

export type LocalMessageMediaState =
  | "idle"
  | "selecting"
  | "preparing"
  | "uploading"
  | "upload_failed"
  | "sending"
  | "send_failed_retryable"
  | "send_failed_permanent"
  | "sent"
  | "cancelled"
  | "unavailable";

/** Durable, media-only retry metadata. It never stores a storage key or a server path. */
export type LocalMessageMediaAttempt = {
  attempt_id: string;
  conversation_id: string;
  client_upload_id: string;
  client_message_id: string;
  media_id: string | null;
  media_type: "video";
  uri: string;
  file_name: string | null;
  mime_type: string;
  file_size_bytes: number;
  width_px: number;
  height_px: number;
  duration_ms: number;
  local_state: LocalMessageMediaState;
  last_error_code: string | null;
  created_at: string;
  updated_at: string;
};

type StoredOutbox = {
  version: 1;
  device_id: string;
  items: LocalMessageOutboxItem[];
};

let storageQueue: Promise<unknown> = Promise.resolve();

function withStorageLock<T>(operation: () => Promise<T>): Promise<T> {
  const next = storageQueue.then(operation, operation);
  storageQueue = next.then(() => undefined, () => undefined);
  return next;
}

function now() {
  return new Date().toISOString();
}

function newId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function retryAt(attemptCount: number) {
  const delayMs = Math.min(60 * 60 * 1000, 1000 * 2 ** Math.min(attemptCount, 10));
  return new Date(Date.now() + delayMs).toISOString();
}

async function readStore(): Promise<StoredOutbox> {
  const raw = await AsyncStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return { version: 1, device_id: newId("device"), items: [] };
  }
  try {
    const parsed = JSON.parse(raw) as Partial<StoredOutbox>;
    if (parsed.version !== 1 || !parsed.device_id || !Array.isArray(parsed.items)) {
      return { version: 1, device_id: newId("device"), items: [] };
    }
    const cutoff = Date.now() - TERMINAL_RETENTION_MS;
    const retained = parsed.items.filter((item) => (
      item.local_state !== "sent" && item.local_state !== "cancelled"
    ) || Date.parse(item.updated_at) >= cutoff);
    return { version: 1, device_id: parsed.device_id, items: retained.slice(-MAX_ITEMS) };
  } catch {
    return { version: 1, device_id: newId("device"), items: [] };
  }
}

async function writeStore(store: StoredOutbox) {
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  return store;
}

export async function getMessageDeviceId() {
  await storageQueue;
  return (await readStore()).device_id;
}

export async function listLocalMessageOutbox() {
  await storageQueue;
  return (await readStore()).items;
}

export async function saveLocalDraft(
  conversationId: string,
  draftText: string,
  message: MessageCreateInput,
) {
  return withStorageLock(async () => {
    const store = await readStore();
    const existing = store.items.find(
      (item) => item.conversation_id === conversationId && item.local_state === "queued" && !item.client_message_id,
    );
    const timestamp = now();
    const item: LocalMessageOutboxItem = existing
      ? { ...existing, draft_text: draftText, message, updated_at: timestamp }
      : {
          local_id: newId("draft"),
          device_id: store.device_id,
          conversation_id: conversationId,
          client_message_id: "",
          message,
          draft_text: draftText,
          local_state: "queued",
          attempt_count: 0,
          next_retry_at: null,
          last_error_code: null,
          server_message_id: null,
          server_event_id: null,
          created_at: timestamp,
          updated_at: timestamp,
        };
    const withoutExisting = store.items.filter((candidate) => candidate.local_id !== item.local_id);
    await writeStore({ ...store, items: [...withoutExisting, item].slice(-MAX_ITEMS) });
    return item;
  });
}

export async function enqueueLocalMessage(
  conversationId: string,
  message: MessageCreateInput,
  draftText = "",
) {
  return withStorageLock(async () => {
    const store = await readStore();
    const timestamp = now();
    const item: LocalMessageOutboxItem = {
      local_id: newId("outbox"),
      device_id: store.device_id,
      conversation_id: conversationId,
      client_message_id: message.client_message_id,
      message,
      draft_text: draftText,
      local_state: "queued",
      attempt_count: 0,
      next_retry_at: null,
      last_error_code: null,
      server_message_id: null,
      server_event_id: null,
      created_at: timestamp,
      updated_at: timestamp,
    };
    await writeStore({ ...store, items: [...store.items, item].slice(-MAX_ITEMS) });
    return item;
  });
}

export async function updateLocalMessageOutbox(
  localId: string,
  patch: Partial<Pick<LocalMessageOutboxItem, "local_state" | "attempt_count" | "next_retry_at" | "last_error_code" | "server_message_id" | "server_event_id">>,
) {
  return withStorageLock(async () => {
    const store = await readStore();
    const timestamp = now();
    const items = store.items.map((item) => item.local_id === localId ? { ...item, ...patch, updated_at: timestamp } : item);
    await writeStore({ ...store, items });
    return items.find((item) => item.local_id === localId) ?? null;
  });
}

export async function removeLocalMessageOutbox(localId: string) {
  return withStorageLock(async () => {
    const store = await readStore();
    await writeStore({ ...store, items: store.items.filter((item) => item.local_id !== localId) });
  });
}

export async function clearLocalDraft(conversationId: string) {
  return withStorageLock(async () => {
    const store = await readStore();
    await writeStore({
      ...store,
      items: store.items.filter((item) => !(item.conversation_id === conversationId && !item.client_message_id)),
    });
  });
}

export async function recoverLocalMessageOutbox() {
  return withStorageLock(async () => {
    const store = await readStore();
    const timestamp = now();
    const items = store.items.map((item) => item.local_state === "sending"
      ? { ...item, local_state: "queued" as const, next_retry_at: timestamp, updated_at: timestamp }
      : item);
    await writeStore({ ...store, items });
    return items;
  });
}

async function readMediaAttempts(): Promise<LocalMessageMediaAttempt[]> {
  const raw = await AsyncStorage.getItem(MEDIA_ATTEMPT_STORAGE_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.slice(-MAX_ITEMS) as LocalMessageMediaAttempt[] : [];
  } catch {
    return [];
  }
}

async function writeMediaAttempts(items: LocalMessageMediaAttempt[]) {
  await AsyncStorage.setItem(MEDIA_ATTEMPT_STORAGE_KEY, JSON.stringify(items.slice(-MAX_ITEMS)));
}

export async function listLocalMessageMediaAttempts(conversationId: string) {
  await storageQueue;
  return (await readMediaAttempts()).filter((item) => item.conversation_id === conversationId);
}

export async function saveLocalMessageMediaAttempt(
  attempt: Omit<LocalMessageMediaAttempt, "attempt_id" | "created_at" | "updated_at">,
) {
  return withStorageLock(async () => {
    const items = await readMediaAttempts();
    const timestamp = now();
    const existing = items.find((item) => item.client_message_id === attempt.client_message_id);
    const next: LocalMessageMediaAttempt = existing
      ? { ...existing, ...attempt, updated_at: timestamp }
      : { ...attempt, attempt_id: newId("media"), created_at: timestamp, updated_at: timestamp };
    await writeMediaAttempts([...items.filter((item) => item.attempt_id !== next.attempt_id), next]);
    return next;
  });
}

export async function removeLocalMessageMediaAttempt(clientMessageId: string) {
  return withStorageLock(async () => writeMediaAttempts(
    (await readMediaAttempts()).filter((item) => item.client_message_id !== clientMessageId),
  ));
}

export function nextRetryForAttempt(attemptCount: number) {
  return retryAt(attemptCount);
}
