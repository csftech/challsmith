import type { NextRequest } from "next/server";

import { API_URL, COOKIE } from "@/server/config";

export async function POST(req: NextRequest) {
  const token = req.cookies.get(COOKIE)?.value;
  if (token) {
    await fetch(`${API_URL}/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    }).catch(() => {}); // the cookie is cleared either way
  }
  return Response.json({ ok: true }, {
    status: 200,
    headers: { "Set-Cookie": `${COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict` },
  });
}
