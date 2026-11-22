import type { NextRequest } from "next/server";

import { API_URL, COOKIE, guard, json } from "@/lib/bff";

export async function POST(req: NextRequest) {
  const denied = guard(req);
  if (denied) return denied;
  let up: Response;
  try {
    up = await fetch(`${API_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await req.text(),
      cache: "no-store",
    });
  } catch {
    return json({ detail: "api unreachable" }, 502);
  }
  if (!up.ok) return json(await up.json().catch(() => ({ detail: "login failed" })), up.status);
  const { token, expires_at } = await up.json();
  // the api sends naive UTC timestamps; treat a missing zone as UTC
  const when = Date.parse(/(Z|[+-]\d\d:?\d\d)$/.test(expires_at) ? expires_at : `${expires_at}Z`);
  const maxAge = Math.max(0, Math.floor((when - Date.now()) / 1000));
  const res = json({ ok: true }, 200);
  res.headers.append(
    "Set-Cookie",
    `${COOKIE}=${token}; Max-Age=${maxAge}; Path=/; HttpOnly; SameSite=Strict`,
  );
  return res;
}
