const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  return (await apiPage<T>(path, init)).data;
}

/** Like api() but also returns the X-Total-Count pagination header (null when absent). */
export async function apiPage<T>(path: string, init?: RequestInit): Promise<{ data: T; total: number | null }> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(0, "Cannot reach the Tratepra backend. Is it running?");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  const total = res.headers?.get?.("X-Total-Count");
  return { data: (await res.json()) as T, total: total != null ? Number(total) : null };
}
