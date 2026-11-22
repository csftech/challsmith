import { API_URL } from "@/server/config";
import { forwardInit, passBack, unreachable } from "@/utils/bff";

export async function GET() {
  try {
    const up = await fetch(`${API_URL}/cleanup/images`, { method: "GET", ...(await forwardInit()) });
    return passBack(up);
  } catch {
    return unreachable();
  }
}
