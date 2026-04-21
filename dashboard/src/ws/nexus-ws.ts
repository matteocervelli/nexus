// Placeholder WebSocket client — full implementation in #23.

type NexusEvent = "workflow.updated" | "agent.status" | "audit.event";
type EventHandler = (data: unknown) => void;

export class NexusWebSocket {
  private readonly _handlers = new Map<NexusEvent, EventHandler[]>();

  connect(_url: string): void {
    throw new Error("NexusWebSocket.connect not implemented — see issue #23");
  }

  disconnect(): void {
    throw new Error(
      "NexusWebSocket.disconnect not implemented — see issue #23",
    );
  }

  on(event: NexusEvent, handler: EventHandler): void {
    const existing = this._handlers.get(event) ?? [];
    this._handlers.set(event, [...existing, handler]);
  }

  off(event: NexusEvent, handler: EventHandler): void {
    const existing = this._handlers.get(event) ?? [];
    this._handlers.set(
      event,
      existing.filter((h) => h !== handler),
    );
  }
}
