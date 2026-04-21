// SSE client for /nexus/api/events.
// Replaces the WebSocket stub from issue #23.

export type NexusEventType =
  | "work_item_status_changed"
  | "workflow_step_updated"
  | "agent_spawned"
  | "agent_completed"
  | "budget_alert";

export interface NexusEventEnvelope {
  type: NexusEventType;
  data: Record<string, unknown>;
  ts: string;
}

type EventHandler = (envelope: NexusEventEnvelope) => void;

const _BASE_DELAY = 1_000;
const _MAX_DELAY = 30_000;

export class NexusEventSource {
  private _es: EventSource | null = null;
  private _handlers = new Map<NexusEventType, Set<EventHandler>>();
  private _retryDelay = _BASE_DELAY;
  private _stopped = false;
  private _retryTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(private readonly _url: string = "/nexus/api/events") {}

  connect(): void {
    this._stopped = false;
    this._open();
  }

  disconnect(): void {
    this._stopped = true;
    if (this._retryTimer !== null) {
      clearTimeout(this._retryTimer);
      this._retryTimer = null;
    }
    this._es?.close();
    this._es = null;
  }

  on(type: NexusEventType, handler: EventHandler): () => void {
    if (!this._handlers.has(type)) {
      this._handlers.set(type, new Set());
    }
    this._handlers.get(type)?.add(handler);
    return () => { this.off(type, handler); };
  }

  off(type: NexusEventType, handler: EventHandler): void {
    this._handlers.get(type)?.delete(handler);
  }

  private _open(): void {
    this._es = new EventSource(this._url);

    this._es.onmessage = (evt) => {
      try {
        const envelope = JSON.parse(evt.data as string) as NexusEventEnvelope;
        this._dispatch(envelope);
        this._retryDelay = _BASE_DELAY;
      } catch {
        // malformed frame — ignore
      }
    };

    this._es.onerror = () => {
      this._es?.close();
      this._es = null;
      if (!this._stopped) {
        this._retryTimer = setTimeout(() => {
          this._retryDelay = Math.min(this._retryDelay * 2, _MAX_DELAY);
          this._open();
        }, this._retryDelay);
      }
    };
  }

  private _dispatch(envelope: NexusEventEnvelope): void {
    const handlers = this._handlers.get(envelope.type);
    handlers?.forEach((h) => { h(envelope); });
  }
}
