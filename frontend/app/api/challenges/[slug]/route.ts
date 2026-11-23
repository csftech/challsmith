import type { NextRequest } from "next/server";

import { API_URL } from "@/server/config";
import { badPath, badSegment, forwardInit, passBack, unreachable } from "@/utils/bff";

type Ctx = { params: Promise<{ slug: string }> };

export async function GET(_req: NextRequest, { params }: Ctx) {
  const { slug } = await params;
  if (badSegment(slug)) return badPath();
  try {
    const up = await fetch(`${API_URL}/challenges/${encodeURIComponent(slug)}`, { method: "GET", ...(await forwardInit()) });
    return passBack(up);
  } catch {
    return unreachable();
  }
}

export async function PUT(req: NextRequest, { params }: Ctx) {
  const { slug } = await params;
  if (badSegment(slug)) return badPath();
  try {
    const up = await fetch(`${API_URL}/challenges/${encodeURIComponent(slug)}${req.nextUrl.search}`, { method: "PUT", ...(await forwardInit(req)) });
    return passBack(up);
  } catch {
    return unreachable();
  }
}

export async function DELETE(_req: NextRequest, { params }: Ctx) {
  const { slug } = await params;
  if (badSegment(slug)) return badPath();
  try {
    const up = await fetch(`${API_URL}/challenges/${encodeURIComponent(slug)}`, { method: "DELETE", ...(await forwardInit()) });
    return passBack(up);
  } catch {
    return unreachable();
  }
}
