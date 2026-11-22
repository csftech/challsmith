import type { NextRequest } from "next/server";

import { API_URL, COOKIE, guard, json } from "@/lib/bff";

type Ctx = { params: Promise<{ path: string[] }> };

async function forward(req: NextRequest, ctx: Ctx) {
  const denied = guard(req);
  if (denied) return denied;
  const { path } = await ctx.params;
  if (path.some((s) => s === "." || s === ".." || s.includes("/"))) return json({ detail: "bad path" }, 400);
  // login/logout only through their own routes, so the raw token never reaches the browser; GET auth/me only names the account
  const me = req.method === "GET" && path.length === 2 && path[1] === "me";
  if (path[0].toLowerCase() === "auth" && !me) return json({ detail: "forbidden" }, 403);
  const token = req.cookies.get(COOKIE)?.value;
  if (!token) return json({ detail: "not logged in" }, 401);
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
