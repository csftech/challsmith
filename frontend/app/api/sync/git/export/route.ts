import type { NextRequest } from "next/server";

import { API_URL } from "@/server/config";
import { forwardInit, passBack, unreachable } from "@/utils/bff";

export async function POST(req: NextRequest) {
  try {
    const up = await fetch(`${API_URL}/sync/git/export`, { method: "POST", ...(await forwardInit(req)) });
    return passBack(up);
  } catch {
    return unreachable();
  }
}
