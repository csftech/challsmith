// Pure response helpers for the BFF route handlers (no cookies, no server-only, so node --test can load them).

// response headers the BFF passes back to the browser; everything else from the api is dropped
export const KEEP_HEADERS = ["content-type", "content-disposition", "content-length"];

// The api's response with only KEEP_HEADERS, same status, body still streamed.
export function passBack(up: Response): Response {
  const out = new Headers();
  for (const h of KEEP_HEADERS) {
    const v = up.headers.get(h);
    if (v) out.set(h, v);
  }
  return new Response(up.body, { status: up.status, headers: out });
}

export const unreachable = () => Response.json({ detail: "api unreachable" }, { status: 502 });

// A path param that could change the backend path once forwarded: ".", ".." or one holding "/".
export const badSegment = (...segments: string[]) => segments.some((s) => s === "." || s === ".." || s.includes("/"));

export const badPath = () => Response.json({ detail: "bad path" }, { status: 400 });
