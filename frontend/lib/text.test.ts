import assert from "node:assert/strict";
import { test } from "node:test";

import { decode, encode } from "./text.ts";

const bytes = (s: string | number[]) => (typeof s === "string" ? new TextEncoder().encode(s) : new Uint8Array(s));

for (const [name, b] of [
  ["LF", bytes("a\nb\n")],
  ["CRLF", bytes("a\r\nb\r\n")],
  ["BOM+LF", bytes([0xef, 0xbb, 0xbf, 0x61, 0x0a])],
  ["BOM+CRLF", bytes([0xef, 0xbb, 0xbf, 0x61, 0x0d, 0x0a, 0x62])],
  ["no trailing newline, utf-8", bytes("你好")],
  ["empty", bytes("")],
] as const) {
  test(`round-trips ${name}`, () => {
    const d = decode(b)!;
    assert.deepEqual(encode(d.text, d.enc), b);
  });
}

test("refuses what it cannot round-trip", () => {
  assert.equal(decode(bytes("a\r\nb\nc")), null); // mixed endings
  assert.equal(decode(bytes("a\rb")), null); // lone CR
  assert.equal(decode(bytes([0xff, 0xfe, 0x00])), null); // not utf-8
});
