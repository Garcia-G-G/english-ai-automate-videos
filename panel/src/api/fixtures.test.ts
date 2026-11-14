/**
 * Writes the demo payloads as JSON fixtures for the Python API's contract tests
 * (WRITE_FIXTURES=1 npx vitest run src/api/fixtures.test.ts). Always checks that
 * the demo data still type-checks against the contract.
 */
import { writeFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { Game, Home, Meta, ReviewList } from "./contract";
import { demoGame, demoHome, demoMeta, demoReview } from "./mock/data";

const payloads: Record<string, Meta | Home | Game | ReviewList> = {
  meta: demoMeta,
  home: demoHome,
  game: demoGame,
  review: demoReview(new Date("2026-11-14T17:00:00-06:00")),
};

describe("contract fixtures", () => {
  it("has one payload per GET endpoint", () => {
    expect(Object.keys(payloads)).toEqual(["meta", "home", "game", "review"]);
    if (process.env.WRITE_FIXTURES === "1") {
      for (const [k, v] of Object.entries(payloads)) writeFileSync(`contract-fixtures/${k}.json`, JSON.stringify(v, null, 2) + "\n");
    }
  });
});
