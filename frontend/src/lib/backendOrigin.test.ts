import { describe, expect, it } from "vitest";

import { resolveBackendOrigin } from "./backendOrigin";

describe("resolveBackendOrigin", () => {
  it("prefers the internal backend URL", () => {
    expect(
      resolveBackendOrigin({
        BACKEND_INTERNAL_URL: "http://backend:3456",
        NEXT_PUBLIC_API_URL: "https://api.example.com",
        NODE_ENV: "production",
      } as NodeJS.ProcessEnv),
    ).toBe("http://backend:3456");
  });

  it("uses the configured public API URL when there is no internal URL", () => {
    expect(
      resolveBackendOrigin({
        NEXT_PUBLIC_API_URL: "https://api.example.com",
        NODE_ENV: "production",
      } as NodeJS.ProcessEnv),
    ).toBe("https://api.example.com");
  });

  it("uses the managed API for Auth0 deploys when no backend URL is configured", () => {
    expect(
      resolveBackendOrigin({
        NEXT_PUBLIC_AUTH0_ENABLED: "true",
        NODE_ENV: "production",
      } as NodeJS.ProcessEnv),
    ).toBe("https://api.joinstash.ai");
  });

  it("uses localhost for generic production self-hosts", () => {
    expect(resolveBackendOrigin({ NODE_ENV: "production" } as NodeJS.ProcessEnv)).toBe(
      "http://localhost:3456",
    );
  });

  it("uses localhost for local development", () => {
    expect(resolveBackendOrigin({ NODE_ENV: "development" } as NodeJS.ProcessEnv)).toBe(
      "http://localhost:3456",
    );
  });
});
