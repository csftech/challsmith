import type { NextRequest } from "next/server";

import { API_URL } from "@/server/config";
import { badPath, badSegment, forwardInit, passBack, unreachable } from "@/utils/bff";

type Ctx = { params: Promise<{ id: string }> };

export async function GET(_req: NextRequest, { params }: Ctx) {
  const { id } = await params;
  if (badSegment(id)) return badPath();
  try {
    const up = await fetch(`${API_URL}/publish-runs/${encodeURIComponent(id)}`, { method: "GET", ...(await forwardInit()) });
    return passBack(up);
  } catch {
    return unreachable();
  }
}
