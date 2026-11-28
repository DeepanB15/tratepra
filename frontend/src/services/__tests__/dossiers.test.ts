import { afterEach, describe, expect, it, vi } from "vitest";
import { createDossier, listDossierClaims, listDossierEvidence, refreshDossier } from "../dossiers";
import { ArticleBadge, QualityCard, claimLabel } from "../../components/dossier/parts";

const res = (body: unknown) => ({ ok: true, status: 200, statusText: "", headers: { get: () => "7" }, json: async () => body }) as unknown as Response;
afterEach(() => vi.unstubAllGlobals());

describe("dossier service", () => {
  it("posts the topic id and omits empty filters from GET queries", async () => {
    const f = vi.fn(async () => res({ id: "d1" }));
    vi.stubGlobal("fetch", f);
    await createDossier({ topic_id: "t1", time_range: "30d" });
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/api\/research\/dossiers$/);
    expect(JSON.parse(init.body as string)).toEqual({ topic_id: "t1", time_range: "30d" });
    await listDossierEvidence("d1", { role: "contradictory", publisher: "", limit: 20, offset: 0 });
    expect((f.mock.calls[1] as unknown as [string])[0]).toMatch(/\/d1\/evidence\?role=contradictory&limit=20$/);
    const page = await listDossierClaims("d1", { status: "unverified" });
    expect(page.total).toBe(7);
    await refreshDossier("d1");
    expect((f.mock.calls[3] as unknown as [string, RequestInit])[1].method).toBe("POST");
  });
});

describe("non-overclaiming labels", () => {
  it("never labels a claim as simply 'verified' or 'true'", () => {
    for (const s of ["supported", "partially_supported", "contradicted", "unverified", "insufficient_evidence"] as const) {
      expect(claimLabel(s).toLowerCase()).not.toMatch(/\b(verified|true|confirmed|proven)\b(?!\))/);
    }
    expect(claimLabel("supported")).toContain("lexical check");
  });
  it("exports visual components", () => {
    expect(typeof QualityCard).toBe("function");
    expect(typeof ArticleBadge).toBe("function");
  });
});
