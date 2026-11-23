import type { NextRequest } from "next/server";

import { API_URL, COOKIE } from "@/server/config";

export async function POST(req: NextRequest) {
  let up: Response;
  try {
    up = await fetch(`${API_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await req.text(),
      cache: "no-store",
    });
  } catch {
    return Response.json({ detail: "api unreachable" }, { status: 502 });
  }
  if (!up.ok) return Response.json(await up.json().catch(() => ({ detail: "login failed" })), { status: up.status });
  const { token, expires_at } = await up.json();
  // the api sends naive UTC timestamps; treat a missing zone as UTC
  const when = Date.parse(/(Z|[+-]\d\d:?\d\d)$/.test(expires_at) ? expires_at : `${expires_at}Z`);
  const maxAge = Math.max(0, Math.floor((when - Date.now()) / 1000));
  const res = Response.json({ ok: true }, { status: 200 });
  res.headers.append(
    "Set-Cookie",
    `${COOKIE}=${token}; Max-Age=${maxAge}; Path=/; HttpOnly; SameSite=Strict`,
  );
  return res;
}
