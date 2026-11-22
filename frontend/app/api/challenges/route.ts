import type { NextRequest } from "next/server";

import { API_URL } from "@/server/config";
import { forwardInit, passBack, unreachable } from "@/utils/bff";

export async function GET() {
  try {
    const up = await fetch(`${API_URL}/challenges`, { method: "GET", ...(await forwardInit()) });
    return passBack(up);
  } catch {
    return unreachable();
  }
}

export async function POST(req: NextRequest) {
  try {
    const up = await fetch(`${API_URL}/challenges`, { method: "POST", ...(await forwardInit(req)) });
    return passBack(up);
  } catch {
    return unreachable();
  }
}
