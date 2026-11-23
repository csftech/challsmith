import assert from "node:assert/strict";
import { test } from "node:test";

import { ApiError, errorText } from "./api.ts";

const t = (key: string) => `T:${key}`;

test("errorText translates a known code", () => {
  assert.equal(errorText(new ApiError(409, "slug exists", undefined, "slug_exists"), t), "T:errors.slug_exists");
});

test("errorText falls back to the message", () => {
  assert.equal(errorText(new ApiError(500, "boom", undefined, "no_such_code"), t), "boom");
  assert.equal(errorText(new ApiError(500, "boom"), t), "boom");
  assert.equal(errorText(new Error("plain"), t), "plain");
});

test("errorText keeps the cause for codes whose detail explains the failure", () => {
  assert.equal(errorText(new ApiError(502, "git: auth failed", "git: auth failed", "sync_failed"), t), "T:errors.sync_failed (git: auth failed)");
  assert.equal(errorText(new ApiError(400, "bad gz", "bad gz", "invalid_archive"), t), "T:errors.invalid_archive (bad gz)");
  assert.equal(errorText(new ApiError(409, "slug already exists", undefined, "slug_exists"), t), "T:errors.slug_exists");
});
