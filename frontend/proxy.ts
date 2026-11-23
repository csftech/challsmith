import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { COOKIE } from "@/server/config";

// DNS-rebinding guard: only these Host values may reach the app (comma-separated, env ALLOWED_HOSTS).
const HOSTS = (process.env.ALLOWED_HOSTS ?? "localhost:3000,127.0.0.1:3000")
  .split(",")
  .map((h) => h.trim().toLowerCase())
  .filter(Boolean);

// CSRF guard for writes: Origin's host must equal the Host the browser addressed.
function sameOrigin(req: NextRequest): boolean {
  if (req.method === "GET" || req.method === "HEAD") return true;
  const origin = req.headers.get("origin");
  if (!origin) return false;
  try {
    return new URL(origin).host === req.headers.get("host");
  } catch {
    return false;
  }
}

// Every request passes here before any page or route handler: Host first, then for /api/* the Origin
// of writes and the session cookie (login and logout need none); pages without a session go to /login.
export function proxy(req: NextRequest) {
  const host = req.headers.get("host");
  if (host === null || !HOSTS.includes(host.toLowerCase())) return new NextResponse("host not allowed", { status: 421 });
  const p = req.nextUrl.pathname;
  if (p.startsWith("/api/")) {
    if (!sameOrigin(req)) return NextResponse.json({ detail: "bad origin" }, { status: 403 });
    if (p !== "/api/login" && p !== "/api/logout" && !req.cookies.get(COOKIE)?.value) {
      return NextResponse.json({ detail: "not logged in" }, { status: 401 });
    }
    return NextResponse.next();
  }
  if (p === "/login" || req.cookies.has(COOKIE)) return NextResponse.next();
  // build the URL from Host: req.url would carry the 0.0.0.0 bind address
  return NextResponse.redirect(new URL("/login", `http://${host}`), 307);
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
