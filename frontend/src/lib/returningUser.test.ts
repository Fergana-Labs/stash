import { describe, expect, it, beforeEach } from "vitest";
import { hasSignedInBefore, markSignedInBefore } from "./returningUser";

// The login page's "Welcome back" copy must never greet a visitor whose
// browser has no record of a prior sign-in (incognito, new machine).
describe("returning-user marker", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("is absent for a fresh browser", () => {
    expect(hasSignedInBefore()).toBe(false);
  });

  it("persists once a sign-in marks it", () => {
    markSignedInBefore();

    expect(hasSignedInBefore()).toBe(true);
  });
});
