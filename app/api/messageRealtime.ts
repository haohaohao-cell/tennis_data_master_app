import { API_BASE_URL } from "@/api/client";

export type RealtimeWakeEnvelope = {
  type: "sync.wake";
  protocol_version: number;
  event_id: string;
  event_type: "message.created" | "message.recalled" | "message.edited" | "message.reaction_changed" | "message.forwarded" | "conversation.read" | "conversation.members_changed";
  sync_required: true;
  conversation_id: string | null;
  message_seq: number | null;
  emitted_at: string;
};

type SocketLike = {
  close: () => void;
  onclose: ((event: { code: number }) => void) | null;
  onerror: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  onopen: (() => void) | null;
  send: (data: string) => void;
};

type RealtimeOptions = {
  createSocket?: (url: string) => SocketLike;
  onWake: () => void;
};

const MAX_RECONNECT_DELAY_MS = 30_000;
const INITIAL_RECONNECT_DELAY_MS = 1_000;
const HEARTBEAT_INTERVAL_MS = 20_000;

export function messageRealtimeUrl(baseUrl = API_BASE_URL) {
  return `${baseUrl.replace(/^http/, "ws")}/api/v1/messages/realtime`;
}

function isWakeEnvelope(value: unknown): value is RealtimeWakeEnvelope {
  if (!value || typeof value !== "object") return false;
  const envelope = value as Partial<RealtimeWakeEnvelope>;
  return (
    envelope.type === "sync.wake" &&
    typeof envelope.event_id === "string" &&
    ["message.created", "message.recalled", "message.edited", "message.reaction_changed", "message.forwarded", "conversation.read", "conversation.members_changed"].includes(envelope.event_type ?? "") &&
    envelope.sync_required === true
  );
}

export class MessageRealtimeCoordinator {
  private accessToken: string | null = null;
  private deviceId: string | null = null;
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private socket: SocketLike | null = null;
  private stopped = true;
  private readonly createSocket: (url: string) => SocketLike;
  private readonly seenEventIds = new Set<string>();

  constructor(private readonly options: RealtimeOptions) {
    this.createSocket = options.createSocket ?? ((url) => new WebSocket(url) as unknown as SocketLike);
  }

  start(accessToken: string, deviceId: string) {
    this.stop();
    this.accessToken = accessToken;
    this.deviceId = deviceId;
    this.stopped = false;
    this.connect();
  }

  stop() {
    this.stopped = true;
    this.accessToken = null;
    this.deviceId = null;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.heartbeat) clearInterval(this.heartbeat);
    this.reconnectTimer = null;
    this.heartbeat = null;
    const socket = this.socket;
    this.socket = null;
    socket?.close();
  }

  private connect() {
    if (this.stopped || !this.accessToken || !this.deviceId) return;
    const socket = this.createSocket(messageRealtimeUrl());
    this.socket = socket;
    socket.onopen = () => {
      if (this.socket !== socket || !this.accessToken || !this.deviceId) return;
      this.reconnectAttempt = 0;
      socket.send(JSON.stringify({ type: "authenticate", access_token: this.accessToken, device_id: this.deviceId }));
      this.heartbeat = setInterval(() => socket.send(JSON.stringify({ type: "ping" })), HEARTBEAT_INTERVAL_MS);
    };
    socket.onmessage = (event) => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(event.data);
      } catch {
        return;
      }
      if (!isWakeEnvelope(parsed) || this.seenEventIds.has(parsed.event_id)) return;
      this.seenEventIds.add(parsed.event_id);
      if (this.seenEventIds.size > 500) this.seenEventIds.delete(this.seenEventIds.values().next().value as string);
      this.options.onWake();
    };
    socket.onerror = () => socket.close();
    socket.onclose = () => {
      if (this.socket !== socket) return;
      if (this.heartbeat) clearInterval(this.heartbeat);
      this.heartbeat = null;
      this.socket = null;
      this.scheduleReconnect();
    };
  }

  private scheduleReconnect() {
    if (this.stopped) return;
    const baseDelay = Math.min(INITIAL_RECONNECT_DELAY_MS * 2 ** this.reconnectAttempt, MAX_RECONNECT_DELAY_MS);
    this.reconnectAttempt += 1;
    const jitter = Math.floor(Math.random() * Math.max(1, Math.floor(baseDelay * 0.25)));
    this.reconnectTimer = setTimeout(() => this.connect(), baseDelay + jitter);
  }
}
