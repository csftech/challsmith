import { cookies } from "next/headers";

import { API_URL, COOKIE, KEEP_HEADERS } from "@/server/config";

export async function GET() {
  const token = (await cookies()).get(COOKIE)?.value; // proxy.ts already answered 401 without one
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  let up: Response;
  try {
    up = await fetch(`${API_URL}/auth/me`, {
      headers,
      redirect: "manual",
      cache: "no-store",
    });
  } catch {
    return Response.json({ detail: "api unreachable" }, { status: 502 });
  }
  const out = new Headers();
  for (const h of KEEP_HEADERS) {
    const v = up.headers.get(h);
    if (v) out.set(h, v);
  }
  return new Response(up.body, { status: up.status, headers: out });
}
