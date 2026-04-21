import "@testing-library/jest-dom";
import { server } from "../mocks/server";

// Stub EventSource globally — jsdom doesn't implement it.
// NexusEventSource uses only onmessage/onerror/close; this stub covers those.
// Tests that need full EventSource behavior (addEventListener etc.) must provide their own stub.
class StubEventSource {
  onmessage: null = null;
  onerror: null = null;
  close() {}
}
vi.stubGlobal("EventSource", StubEventSource);

beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
});
afterEach(() => {
  server.resetHandlers();
});
afterAll(() => {
  server.close();
});
