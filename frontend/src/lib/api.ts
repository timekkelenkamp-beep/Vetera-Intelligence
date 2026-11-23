// Dunne fetch-laag. De browser praat alleen met de lokale backend; API-sleutels blijven server-side.
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `Er ging iets mis (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
      else if (Array.isArray(body.detail)) msg = body.detail.map((d: any) => d.msg).join(", ");
    } catch {
      /* geen JSON */
    }
    throw new ApiError(res.status, msg);
  }
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("application/json") ? res.json() : (res.text() as any)) as Promise<T>;
}

function qs(params?: Record<string, any>) {
  if (!params) return "";
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const api = {
  get: <T = any>(path: string, params?: Record<string, any>) => fetch(`/api${path}${qs(params)}`).then((r) => handle<T>(r)),
  post: <T = any>(path: string, body?: any) =>
    fetch(`/api${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) }).then((r) => handle<T>(r)),
  patch: <T = any>(path: string, body: any) =>
    fetch(`/api${path}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => handle<T>(r)),
  del: <T = any>(path: string) => fetch(`/api${path}`, { method: "DELETE" }).then((r) => handle<T>(r)),
  upload: <T = any>(path: string, form: FormData) => fetch(`/api${path}`, { method: "POST", body: form }).then((r) => handle<T>(r)),
  url: (path: string, params?: Record<string, any>) => `/api${path}${qs(params)}`,
};
