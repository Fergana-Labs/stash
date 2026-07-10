import { describe, expect, it } from "vitest";
import type { SessionData } from "@auth0/nextjs-auth0/types";

import {
  SESSION_ABSOLUTE_SECONDS,
  SESSION_INACTIVITY_SECONDS,
  decryptSessionData,
  encryptSessionData,
  sessionExpiresAt,
} from "../../managed/auth0/sessionStore";

const SESSION: SessionData = {
  user: { sub: "auth0|abc" },
  tokenSet: { accessToken: "at", refreshToken: "rt", expiresAt: 1_700_000_000 },
  internal: { sid: "sid-1", createdAt: 1_700_000_000 },
};

describe("sessionExpiresAt", () => {
  // Rolling sessions slide forward with activity: each write pushes expiry
  // out by the idle window.
  it("extends a fresh session by the inactivity window", () => {
    const createdAt = 1_700_000_000;
    const now = createdAt * 1000;

    expect(sessionExpiresAt(createdAt, now).getTime()).toBe(
      now + SESSION_INACTIVITY_SECONDS * 1000,
    );
  });

  // The SOC 2 control: no amount of activity may extend a session past the
  // absolute cap after login.
  it("never extends past the absolute cap, no matter how active", () => {
    const createdAt = 1_700_000_000;
    const nearEndOfLife = (createdAt + SESSION_ABSOLUTE_SECONDS - 60) * 1000;

    expect(sessionExpiresAt(createdAt, nearEndOfLife).getTime()).toBe(
      (createdAt + SESSION_ABSOLUTE_SECONDS) * 1000,
    );
  });
});

describe("session data encryption", () => {
  // Sessions hold Auth0 access/refresh tokens; a database dump must not
  // expose them in the clear.
  it("round-trips session data and produces no plaintext tokens", () => {
    const encrypted = encryptSessionData(SESSION, "test-secret");

    expect(encrypted).not.toContain("at");
    expect(encrypted).not.toContain("rt");
    expect(decryptSessionData(encrypted, "test-secret")).toEqual(SESSION);
  });

  // A rotated AUTH0_SECRET must sign users out, not take the app down.
  it("treats data encrypted under a different secret as no session", () => {
    const encrypted = encryptSessionData(SESSION, "old-secret");

    expect(decryptSessionData(encrypted, "new-secret")).toBeNull();
  });
});
