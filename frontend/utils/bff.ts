import "server-only";

import { cookies } from "next/headers";
import type { NextRequest } from "next/server";

import { COOKIE } from "@/server/config";

export { badPath, badSegment, passBack, unreachable } from "@/utils/http";

// The fixed fetch options for a call to the api: the session as a bearer token (proxy.ts already
// answered 401 without one; the browser's Cookie is never forwarded), and, given the request, its
// Content-Type and its body streamed through unbuffered.
export async function forwardInit(req?: NextRequest): Promise<RequestInit> {
  const headers: Record<string, string> = { Authorization: `Bearer ${(await cookies()).get(COOKIE)?.value}` };
  const type = req?.headers.get("content-type");
  if (type) headers["Content-Type"] = type;
  return {
    headers,
    redirect: "manual",
    cache: "no-store",
    ...(req?.body ? { body: req.body, duplex: "half" } : {}),
  } as RequestInit;
}
