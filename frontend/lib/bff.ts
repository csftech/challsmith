import type { NextRequest } from "next/server";

export const API_URL = process.env.API_URL ?? "http://api:8000";
export const COOKIE = "challsmith_session";

// DNS-rebinding guard: only these Host values may reach the BFF (comma-separated, env ALLOWED_HOSTS).
const HOSTS = (process.env.ALLOWED_HOSTS ?? "localhost:3000,127.0.0.1:3000")
  .split(",")
  .map((h) => h.trim().toLowerCase())
  .filter(Boolean);

export function allowedHost(host: string | null): boolean {
  return host !== null && HOSTS.includes(host.toLowerCase());
}

// CSRF guard for writes: Origin's host must equal the Host the browser addressed.
export function sameOrigin(req: NextRequest): boolean {
  if (req.method === "GET" || req.method === "HEAD") return true;
  const origin = req.headers.get("origin");
  if (!origin) return false;
  try {
    return new URL(origin).host === req.headers.get("host");
  } catch {
    return false;
  }
}

// Applied to every request: Host allow-list first, then Origin for writes. Null = ok.
export function guard(req: NextRequest): Response | null {
  if (!allowedHost(req.headers.get("host"))) return json({ detail: "host not allowed" }, 421);
  if (!sameOrigin(req)) return json({ detail: "bad origin" }, 403);
  return null;
}

export const json = (body: unknown, status: number, headers?: HeadersInit) =>
  Response.json(body, { status, headers });
