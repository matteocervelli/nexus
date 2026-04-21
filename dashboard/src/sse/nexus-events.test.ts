import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { NexusEventSource } from "./nexus-events";

class MockEventSource {
  static instances: MockEventSource[] = [];
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(public url: string) {
    MockEventSource.instances.push(this);
  }

  close() {
    this.closed = true;
  }

  emit(data: string) {
    this.onmessage?.({ data });
  }

  triggerError() {
    this.onerror?.();
  }
}

describe("NexusEventSource", () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    vi.stubGlobal("EventSource", MockEventSource);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("dispatches events to registered handlers", () => {
    const source = new NexusEventSource("/nexus/api/events");
    const handler = vi.fn();
    source.on("agent_spawned", handler);
    source.connect();

    const mock = MockEventSource.instances[0] as MockEventSource;
    mock.emit(
      JSON.stringify({
        type: "agent_spawned",
        data: { work_item_id: "wi-1" },
        ts: "2026-04-21T10:00:00Z",
      }),
    );

    expect(handler).toHaveBeenCalledOnce();
    expect(handler.mock.calls[0]?.[0]).toMatchObject({ type: "agent_spawned" });
  });

  it("does not dispatch to unrelated event handlers", () => {
    const source = new NexusEventSource();
    const handler = vi.fn();
    source.on("budget_alert", handler);
    source.connect();

    const mock = MockEventSource.instances[0] as MockEventSource;
    mock.emit(JSON.stringify({ type: "agent_spawned", data: {}, ts: "" }));

    expect(handler).not.toHaveBeenCalled();
  });

  it("unsubscribes via returned cleanup function", () => {
    const source = new NexusEventSource();
    const handler = vi.fn();
    const off = source.on("agent_completed", handler);
    source.connect();
    off();

    const mock = MockEventSource.instances[0] as MockEventSource;
    mock.emit(JSON.stringify({ type: "agent_completed", data: {}, ts: "" }));

    expect(handler).not.toHaveBeenCalled();
  });

  it("ignores malformed JSON frames", () => {
    const source = new NexusEventSource();
    source.connect();
    const mock = MockEventSource.instances[0] as MockEventSource;
    expect(() => { mock.emit("not-json"); }).not.toThrow();
  });

  it("closes EventSource on disconnect", () => {
    const source = new NexusEventSource();
    source.connect();
    const mock = MockEventSource.instances[0] as MockEventSource;
    source.disconnect();
    expect(mock.closed).toBe(true);
  });

  it("does not reconnect after disconnect", () => {
    vi.useFakeTimers();
    const source = new NexusEventSource();
    source.connect();
    source.disconnect();
    const mock = MockEventSource.instances[0] as MockEventSource;
    mock.triggerError();
    vi.advanceTimersByTime(5_000);
    expect(MockEventSource.instances).toHaveLength(1);
    vi.useRealTimers();
  });
});
