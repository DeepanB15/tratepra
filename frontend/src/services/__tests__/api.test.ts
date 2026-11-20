import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api";
import { fmtAge } from "../../components/common/ui";

function mockFetch(impl: () => Promise<unknown>) {
  vi.stubGlobal("fetch", vi.fn(impl));
}
const res = (status: number, body: unknown, statusText = "") =>
  ({ ok: status < 400, status, statusText, json: async () => body }) as unknown as Response;

afterEach(() => vi.unstubAllGlobals());

describe("api()", () => {
  it("returns parsed JSON on success", async () => {
    mockFetch(async () => res(200, { ok: 1 }));
    expect(await api<{ ok: number }>("/x")).toEqual({ ok: 1 });
  });

  it("surfaces a string detail from the backend as an ApiError", async () => {
    mockFetch(async () => res(422, { detail: "Query contains no searchable terms" }));
    await expect(api("/x")).rejects.toMatchObject({ status: 422, message: "Query contains no searchable terms" });
  });

  it("stringifies structured validation details", async () => {
    mockFetch(async () => res(422, { detail: [{ loc: ["body", "query"], msg: "too short" }] }));
    await expect(api("/x")).rejects.toThrow(/too short/);
  });

  it("falls back to statusText when the error body is not JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 502, statusText: "Bad Gateway", json: async () => { throw new Error("no"); } })));
    await expect(api("/x")).rejects.toMatchObject({ status: 502, message: "Bad Gateway" });
  });

  it("reports an unreachable backend with status 0", async () => {
    mockFetch(async () => { throw new TypeError("Failed to fetch"); });
    const err = (await api("/x").catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
    expect(err.message).toMatch(/Cannot reach/);
  });
});

describe("fmtAge()", () => {
  const now = new Date("2026-01-10T12:00:00Z").getTime();
  it("handles missing, minutes, hours and days", () => {
    expect(fmtAge(null, now)).toBe("never");
    expect(fmtAge("2026-01-10T11:30:00Z", now)).toBe("30 min ago");
    expect(fmtAge("2026-01-10T06:00:00Z", now)).toBe("6 h ago");
    expect(fmtAge("2026-01-05T12:00:00Z", now)).toBe("5 d ago");
  });
});
