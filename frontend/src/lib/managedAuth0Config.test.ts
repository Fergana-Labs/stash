import { describe, expect, it } from "vitest";

import {
  requireAudience,
  requireHttpsAppBaseUrl,
  requireManagedAuth0Config,
} from "../../managed/auth0/config";

describe("managed Auth0 config", () => {
  it("requires an Auth0 audience", () => {
    expect(() => requireAudience({} as NodeJS.ProcessEnv)).toThrow(
      "AUTH0_AUDIENCE must be set",
    );
  });

  it("requires an app base URL", () => {
    expect(() => requireHttpsAppBaseUrl({} as NodeJS.ProcessEnv)).toThrow(
      "APP_BASE_URL must be set",
    );
  });

  it("rejects non-HTTPS app base URLs", () => {
    expect(() =>
      requireHttpsAppBaseUrl({ APP_BASE_URL: "http://app.example.com" } as unknown as NodeJS.ProcessEnv),
    ).toThrow("APP_BASE_URL must be an HTTPS origin");
  });

  it("rejects app base URLs with paths", () => {
    expect(() =>
      requireHttpsAppBaseUrl({
        APP_BASE_URL: "https://app.example.com/settings",
      } as unknown as NodeJS.ProcessEnv),
    ).toThrow("APP_BASE_URL must be an HTTPS origin");
  });

  it("accepts managed Auth0 HTTPS origin config", () => {
    expect(
      requireManagedAuth0Config({
        AUTH0_AUDIENCE: "https://api.example.com",
        APP_BASE_URL: "https://app.example.com/",
      } as unknown as NodeJS.ProcessEnv),
    ).toEqual({ audience: "https://api.example.com" });
  });
});
