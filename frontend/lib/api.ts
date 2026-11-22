import messages from "../messages/zh-TW.json" with { type: "json" };

// plain fields, not parameter properties: node --test strips types and cannot run those
export class ApiError extends Error {
  status: number;
  detail?: unknown;
  code?: string;
  constructor(status: number, message: string, detail?: unknown, code?: string) {
    super(message);
    this.status = status;
    this.detail = detail;
    this.code = code;
  }
}

// codes whose English detail carries the cause (git or docker output, the CTFd error, the bad field)
const WITH_CAUSE = new Set(["sync_failed", "cleanup_failed", "cleanup_plan_failed", "ctfd_unreachable",
  "ctfd_order_failed", "slug_reserved", "bad_gateway"]);

// Translated text for a backend error code, else the raw message (backend detail stays English).
export function errorText(e: unknown, t: (key: string, values?: Record<string, string>) => string): string {
  const code = e instanceof ApiError ? e.code : undefined;
  if (code && Object.hasOwn(messages.errors, code)) {
    const text = t(`errors.${code}`);
    const cause = (e as ApiError).message;
    return (WITH_CAUSE.has(code) || code.startsWith("invalid_")) && cause ? `${text} (${cause})` : text;
  }
  return e instanceof Error ? e.message : String(e);
}

function message(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI 422: [{loc, msg}]
    return detail.map((d) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("\n");
  }
  return detail ? JSON.stringify(detail) : fallback;
}

// Raw call to the BFF; a 401 sends the browser to the login page.
export async function apiRaw(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`/api${path}`, init);
  if (res.status === 401) {
    window.location.href = "/login";
    throw new ApiError(401, "unauthorized", undefined, "unauthorized");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, message(body.detail, `HTTP ${res.status}`), body.detail, body.code);
  }
  return res;
}

export async function api<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiRaw(path, init);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const jsonInit = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export type Summary = {
  slug: string;
  name: string;
  category: string;
  scenario: string;
  publish: "draft" | "published" | "modified";
  sync: "never" | "synced" | "modified";
  updated_at: string;
  position: number;
  ctfd_id: number | null;
  ctfd_missing: boolean;
  template: string | null;
  services: number;
  value: number;
};
export type ListResponse = { items: Summary[]; ctfd_ok: boolean };
export type Template = { name: string; description: string; scenario: string };
export type Service = {
  name: string;
  port: number | null;
  entry: boolean;
  image: string | null;
  env: Record<string, string>;
};
export type Meta = {
  slug: string;
  name: string;
  category: string;
  tags: string[];
  description: string;
  value: number;
  template: string | null;
  scenario: "single" | "multi";
  flag: string;
  flag_prefix: string;
  protocol: "http" | "tcp";
  instance: { timeout: number; mana: number; memory: string; cpus: string };
  services: Service[];
  visible: boolean;
};
export type Detail = { meta: Meta; files: { path: string; size: number }[]; status: unknown };

export const fileUrl = (slug: string, path: string) =>
  `/challenges/${encodeURIComponent(slug)}/files/${path.split("/").map(encodeURIComponent).join("/")}`;

export async function logout() {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
}
