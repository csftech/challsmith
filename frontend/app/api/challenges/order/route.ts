import type { NextRequest } from "next/server";

import { API_URL } from "@/server/config";
import { forwardInit, passBack, unreachable } from "@/utils/bff";

export async function PUT(req: NextRequest) {
  try {
    const up = await fetch(`${API_URL}/challenges/order`, { method: "PUT", ...(await forwardInit(req)) });
    return passBack(up);
  } catch {
    return unreachable();
  }
}
