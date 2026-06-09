import {
  allowedLandingParentOrigin,
  landingAuthStatusMessage,
  LANDING_AUTH_MESSAGE_TYPE,
} from "./landingAuthCheck";

describe("landing auth check", () => {
  it("allows the production marketing origins", () => {
    expect(allowedLandingParentOrigin("https://joinstash.ai")).toBe("https://joinstash.ai");
    expect(allowedLandingParentOrigin("https://www.joinstash.ai/path")).toBe(
      "https://www.joinstash.ai",
    );
  });

  it("allows local marketing origins", () => {
    expect(allowedLandingParentOrigin("http://localhost:3100")).toBe("http://localhost:3100");
    expect(allowedLandingParentOrigin("http://127.0.0.1:3100")).toBe(
      "http://127.0.0.1:3100",
    );
  });

  it("rejects untrusted origins", () => {
    expect(allowedLandingParentOrigin("https://evil.example")).toBeNull();
    expect(allowedLandingParentOrigin("http://joinstash.ai")).toBeNull();
    expect(allowedLandingParentOrigin("not a url")).toBeNull();
  });

  it("builds the postMessage payload", () => {
    expect(landingAuthStatusMessage(true)).toEqual({
      type: LANDING_AUTH_MESSAGE_TYPE,
      signedIn: true,
    });
  });
});
