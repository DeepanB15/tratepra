import { afterEach, describe, expect, it, vi } from "vitest";
import { apiPage } from "../api";
import { buildQuery, searchTrends } from "../trends";
import { fmtPct } from "../../components/common/ui";

afterEach(() => vi.unstubAllGlobals());

describe("buildQuery()", () => {
  it("omits empty, zero and undefined values but keeps meaningful ones", () => {
    expect(buildQuery({ q: "", lifecycle: "emerging", min_sources: 0, offset: 0, limit: 20, is_new: true, min_score: undefined })).toBe("?lifecycle=emerging&limit=20&is_new=true");
    expect(buildQuery({})).toBe("");
  });
});

describe("apiPage()", () => {
  it("returns the X-Total-Count header as a number", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, headers: new Headers({ "X-Total-Count": "42" }), json: async () => [1, 2] })));
    expect(await apiPage<number[]>("/x")).toEqual({ data: [1, 2], total: 42 });
  });
  it("returns null total when the header is absent", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, headers: new Headers(), json: async () => [] })));
    expect((await apiPage("/x")).total).toBeNull();
  });
});

describe("searchTrends()", () => {
  it("requests /api/trends with the filters and sort", async () => {
    const f = vi.fn(async () => ({ ok: true, status: 200, headers: new Headers({ "X-Total-Count": "1" }), json: async () => [] }));
    vi.stubGlobal("fetch", f);
    await searchTrends({ lifecycle: "emerging", sort: "momentum", order: "desc", limit: 5 });
    expect((f.mock.calls[0] as unknown as [string])[0]).toMatch(/\/api\/trends\?lifecycle=emerging&sort=momentum&order=desc&limit=5$/);
  });
});

describe("fmtPct()", () => {
  it("formats signed percentages and missing values", () => {
    expect(fmtPct(50)).toBe("+50%");
    expect(fmtPct(-25.4)).toBe("-25%");
    expect(fmtPct(null)).toBe("—");
  });
});
