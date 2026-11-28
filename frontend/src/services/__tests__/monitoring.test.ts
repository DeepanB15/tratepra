import { afterEach, describe, expect, it, vi } from "vitest";
import { EVENT_LABELS, follow, listNotifications, listWatchlist, markAllRead, patchNotification, setEventState, unreadCount } from "../monitoring";

function mockFetch(body: unknown, status = 200, headers: Record<string, string> = {}) {
  const f = vi.fn().mockImplementation(async () => new Response(JSON.stringify(body), { status, headers }));
  vi.stubGlobal("fetch", f);
  return f;
}
afterEach(() => vi.unstubAllGlobals());

describe("monitoring service", () => {
  it("follows with priority and note via POST", async () => {
    const f = mockFetch({ topic_id: "t1" }, 201);
    await follow("t1", "high", "n");
    const [url, init] = f.mock.calls[0];
    expect(url).toContain("/api/monitoring/watchlist");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ topic_id: "t1", priority: "high", user_note: "n" });
  });
  it("lists the watchlist with filters and reads X-Total-Count", async () => {
    const f = mockFetch([], 200, { "X-Total-Count": "7" });
    const r = await listWatchlist({ q: "ai", enabled: false, priority: "", limit: 25 });
    expect(f.mock.calls[0][0]).toContain("q=ai");
    expect(f.mock.calls[0][0]).toContain("enabled=false");
    expect(f.mock.calls[0][0]).not.toContain("priority=");
    expect(r.total).toBe(7);
  });
  it("keeps event state and notification state on separate endpoints", async () => {
    const f = mockFetch({});
    await setEventState("e1", "dismissed");
    await patchNotification("n1", { read: true });
    expect(f.mock.calls[0][0]).toContain("/events/e1");
    expect(f.mock.calls[1][0]).toContain("/notifications/n1");
  });
  it("reads unread count and marks all read", async () => {
    mockFetch({ unread: 3, by_severity: {} });
    expect((await unreadCount()).unread).toBe(3);
    const f = mockFetch({ marked: 3 });
    await markAllRead();
    expect(f.mock.calls[0][1].method).toBe("POST");
    await listNotifications({ status: "all" });
  });
  it("labels every event type shown by the backend", () => {
    for (const k of ["growth_acceleration", "activity_spike", "monitoring_failure", "contradictory_evidence"]) expect(EVENT_LABELS[k]).toBeTruthy();
  });
});
