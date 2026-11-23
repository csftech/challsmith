import assert from "node:assert/strict";
import { test } from "node:test";

import { badPath, badSegment, KEEP_HEADERS, passBack, unreachable } from "./http.ts";

test("badSegment rejects segments that would change the backend path", () => {
  for (const s of [".", "..", "a/b", "/", "../x"]) assert.equal(badSegment(s), true, s);
  assert.equal(badSegment("slug", "services", "app", "index.php"), false);
  assert.equal(badSegment("ok", ".."), true);
  assert.equal(badSegment("..."), false);
  assert.equal(badSegment(".env"), false);
});

test("passBack keeps status, body and only the allowed headers", async () => {
  const up = new Response("data", {
    status: 201,
    headers: {
      "content-type": "application/gzip",
      "content-disposition": 'attachment; filename="b.tar.gz"',
      "set-cookie": "a=b",
      server: "uvicorn",
    },
  });
  const res = passBack(up);
  assert.equal(res.status, 201);
  assert.equal(await res.text(), "data");
  assert.equal(res.headers.get("content-type"), "application/gzip");
  assert.equal(res.headers.get("content-disposition"), 'attachment; filename="b.tar.gz"');
  assert.equal(res.headers.get("set-cookie"), null);
  assert.equal(res.headers.get("server"), null);
  assert.deepEqual(KEEP_HEADERS, ["content-type", "content-disposition", "content-length"]);
});

test("unreachable and badPath answer like the old catch-all", async () => {
  assert.equal(unreachable().status, 502);
  assert.deepEqual(await unreachable().json(), { detail: "api unreachable" });
  assert.equal(badPath().status, 400);
  assert.deepEqual(await badPath().json(), { detail: "bad path" });
});
