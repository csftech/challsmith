import type { NextRequest } from "next/server";

import { API_URL } from "@/server/config";
import { forwardInit, passBack, unreachable } from "@/utils/bff";

export async function GET() {
  try {
    const up = await fetch(`${API_URL}/settings/git`, { method: "GET", ...(await forwardInit()) });
    return passBack(up);
  } catch {
    return unreachable();
  }
}

export async function PUT(req: NextRequest) {
  try {
    const up = await fetch(`${API_URL}/settings/git`, { method: "PUT", ...(await forwardInit(req)) });
    return passBack(up);
  } catch {
    return unreachable();
  }
}
