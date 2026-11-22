import type { NextRequest } from "next/server";

import { API_URL, COOKIE, json, sameOrigin } from "@/lib/bff";

export async function POST(req: NextRequest) {
  if (!sameOrigin(req)) return json({ detail: "bad origin" }, 403);
  const token = req.cookies.get(COOKIE)?.value;
  if (token) {
    await fetch(`${API_URL}/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    }).catch(() => {}); // the cookie is cleared either way
  }
  return json({ ok: true }, 200, {
    "Set-Cookie": `${COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict`,
  });
}
