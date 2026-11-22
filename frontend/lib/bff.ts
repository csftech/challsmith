import type { NextRequest } from "next/server";

export const API_URL = process.env.API_URL ?? "http://api:8000";
export const COOKIE = "challsmith_session";

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

export const json = (body: unknown, status: number, headers?: HeadersInit) =>
  Response.json(body, { status, headers });
