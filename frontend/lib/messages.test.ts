import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const load = (locale: string) =>
  JSON.parse(readFileSync(new URL(`../messages/${locale}.json`, import.meta.url), "utf8"));

// every leaf as "a.b.c" -> value
function leaves(o: Record<string, unknown>, prefix = ""): Map<string, unknown> {
  const out = new Map<string, unknown>();
  for (const [k, v] of Object.entries(o)) {
    const p = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object") for (const [kk, vv] of leaves(v as Record<string, unknown>, p)) out.set(kk, vv);
    else out.set(p, v);
  }
  return out;
}

const zh = leaves(load("zh-TW"));
const en = leaves(load("en"));

test("zh-TW and en have the same keys", () => {
  assert.deepEqual([...zh.keys()].sort(), [...en.keys()].sort());
});

test("no message is empty", () => {
  for (const [name, m] of [["zh-TW", zh], ["en", en]] as const) {
    for (const [k, v] of m) assert.ok(typeof v === "string" && v.trim() !== "", `${name}: ${k}`);
  }
});
