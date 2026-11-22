import type { NextRequest } from "next/server";

import { API_URL } from "@/server/config";
import { badPath, badSegment, forwardInit, passBack, unreachable } from "@/utils/bff";

type Ctx = { params: Promise<{ slug: string }> };

export async function POST(req: NextRequest, { params }: Ctx) {
  const { slug } = await params;
  if (badSegment(slug)) return badPath();
  try {
    const up = await fetch(`${API_URL}/challenges/${encodeURIComponent(slug)}/publish`, { method: "POST", ...(await forwardInit(req)) });
    return passBack(up);
  } catch {
    return unreachable();
  }
}
