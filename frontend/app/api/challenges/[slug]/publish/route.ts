import type { NextRequest } from "next/server";
import { cookies } from "next/headers";

import { API_URL, COOKIE, KEEP_HEADERS } from "@/server/config";

type Ctx = { params: Promise<{ slug: string }> };

export async function POST(req: NextRequest, { params }: Ctx) {
  const { slug } = await params;
  if (slug === "." || slug === ".." || slug.includes("/")) return Response.json({ detail: "bad path" }, { status: 400 });
  const token = (await cookies()).get(COOKIE)?.value; // proxy.ts already answered 401 without one
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  const type = req.headers.get("content-type");
  if (type) headers["Content-Type"] = type;
  let up: Response;
  try {
    up = await fetch(`${API_URL}/challenges/${encodeURIComponent(slug)}/publish`, {
      method: "POST",
      headers,
      body: req.body, // streamed, not buffered
      duplex: "half",
      redirect: "manual",
      cache: "no-store",
    } as RequestInit);
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
