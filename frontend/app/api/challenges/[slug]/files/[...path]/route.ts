import type { NextRequest } from "next/server";

import { API_URL } from "@/server/config";
import { badPath, badSegment, forwardInit, passBack, unreachable } from "@/utils/bff";

type Ctx = { params: Promise<{ slug: string; path: string[] }> };

export async function GET(_req: NextRequest, { params }: Ctx) {
  const { slug, path } = await params;
  if (badSegment(slug, ...path)) return badPath();
  try {
    const up = await fetch(`${API_URL}/challenges/${encodeURIComponent(slug)}/files/${path.map(encodeURIComponent).join("/")}`, { method: "GET", ...(await forwardInit()) });
    return passBack(up);
  } catch {
    return unreachable();
  }
}

export async function PUT(req: NextRequest, { params }: Ctx) {
  const { slug, path } = await params;
  if (badSegment(slug, ...path)) return badPath();
  try {
    const up = await fetch(`${API_URL}/challenges/${encodeURIComponent(slug)}/files/${path.map(encodeURIComponent).join("/")}`, { method: "PUT", ...(await forwardInit(req)) });
    return passBack(up);
  } catch {
    return unreachable();
  }
}

export async function DELETE(_req: NextRequest, { params }: Ctx) {
  const { slug, path } = await params;
  if (badSegment(slug, ...path)) return badPath();
  try {
    const up = await fetch(`${API_URL}/challenges/${encodeURIComponent(slug)}/files/${path.map(encodeURIComponent).join("/")}`, { method: "DELETE", ...(await forwardInit()) });
    return passBack(up);
  } catch {
    return unreachable();
  }
}
