import type { NextRequest } from "next/server";

import { API_URL, COOKIE, json, sameOrigin } from "@/lib/bff";

type Ctx = { params: Promise<{ path: string[] }> };

async function forward(req: NextRequest, ctx: Ctx) {
  if (!sameOrigin(req)) return json({ detail: "bad origin" }, 403);
  const token = req.cookies.get(COOKIE)?.value;
  if (!token) return json({ detail: "not logged in" }, 401);
  const { path } = await ctx.params;
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` }; // never forward Cookie
  const type = req.headers.get("content-type");
  if (type) headers["Content-Type"] = type;
  const hasBody = req.method !== "GET" && req.method !== "HEAD" && req.body;
  let up: Response;
  try {
    up = await fetch(`${API_URL}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`, {
      method: req.method,
      headers,
      redirect: "manual",
      cache: "no-store",
      ...(hasBody ? { body: req.body, duplex: "half" } : {}),
    } as RequestInit);
  } catch {
    return json({ detail: "api unreachable" }, 502);
  }
  const out = new Headers();
  for (const h of ["content-type", "content-disposition", "content-length"]) {
    const v = up.headers.get(h);
    if (v) out.set(h, v);
  }
  return new Response(up.body, { status: up.status, headers: out });
}

export { forward as GET, forward as POST, forward as PUT, forward as PATCH, forward as DELETE };
