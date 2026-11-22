import assert from "node:assert/strict";
import { test } from "node:test";

import { pickLocale, pickTheme } from "./prefs.ts";

test("pickTheme keeps known themes and falls back to signal", () => {
  assert.equal(pickTheme(undefined), "signal");
  assert.equal(pickTheme("zinc"), "zinc");
  assert.equal(pickTheme("frost"), "frost");
  assert.equal(pickTheme("purple"), "signal");
});

test("pickLocale keeps known locales and falls back to zh-TW", () => {
  assert.equal(pickLocale("en"), "en");
  assert.equal(pickLocale("fr"), "zh-TW");
  assert.equal(pickLocale(undefined), "zh-TW");
});
