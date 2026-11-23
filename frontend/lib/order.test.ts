import assert from "node:assert/strict";
import { test } from "node:test";

import type { Summary } from "./api.ts";
import { flatten, groupByCategory, matches, moveGroup, moveItem } from "./order.ts";

const item = (slug: string, category: string, name = slug, publish: Summary["publish"] = "draft"): Summary => ({
  slug, name, category, publish, scenario: "single", sync: "never", updated_at: "", position: 0,
  ctfd_id: null, ctfd_missing: false, template: null, services: 1, value: 100,
});
const items = [item("a", "web"), item("x", "pwn"), item("b", "web")];

test("groupByCategory keeps first-seen category order and in-group order", () => {
  const groups = groupByCategory(items);
  assert.deepEqual(groups.map((g) => g.category), ["web", "pwn"]);
  assert.deepEqual(groups[0].items.map((i) => i.slug), ["a", "b"]);
  assert.deepEqual(flatten(groups), ["a", "b", "x"]);
});

test("moveItem moves within a category", () => {
  assert.deepEqual(flatten(moveItem(groupByCategory(items), "web", 0, 1)), ["b", "a", "x"]);
});

test("moveGroup moves a whole category", () => {
  assert.deepEqual(flatten(moveGroup(groupByCategory(items), 0, 1)), ["x", "a", "b"]);
});

test("an empty category is its own group", () => {
  const groups = groupByCategory([item("a", "web"), item("n", ""), item("b", "web")]);
  assert.deepEqual(groups.map((g) => g.category), ["web", ""]);
  assert.deepEqual(groups[1].items.map((i) => i.slug), ["n"]);
});

test("matches name, slug, category and status", () => {
  const it = item("sqli-02", "web", "SQL Injection", "published");
  assert.ok(matches(it, "injec", null, null));
  assert.ok(!matches(it, "xss", null, null));
  assert.ok(matches(it, "SQLI-0", null, null));
  assert.ok(!matches(it, "sqli-03", null, null));
  assert.ok(matches(it, "", "web", null));
  assert.ok(!matches(it, "", "pwn", null));
  assert.ok(matches(it, "", null, "published"));
  assert.ok(!matches(it, "", null, "draft"));
});
