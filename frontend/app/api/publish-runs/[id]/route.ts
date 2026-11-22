import type { NextRequest } from "next/server";
import { cookies } from "next/headers";

import { API_URL, COOKIE, KEEP_HEADERS } from "@/server/config";

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_req: NextRequest, { params }: Ctx) {
  const { id } = await params;
  if (id === "." || id === ".." || id.includes("/")) return Response.json({ detail: "bad path" }, { status: 400 });
  const token = (await cookies()).get(COOKIE)?.value; // proxy.ts already answered 401 without one
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  let up: Response;
  try {
    up = await fetch(`${API_URL}/publish-runs/${encodeURIComponent(id)}`, {
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
