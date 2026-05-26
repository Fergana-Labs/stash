import { afterAll, beforeAll, describe, expect, it } from "vitest";

let resolveBackendOrigin: typeof import("./backendOrigin").resolveBackendOrigin;
const originalBackendInternalUrl = process.env.BACKEND_INTERNAL_URL;

beforeAll(async () => {
  process.env.BACKEND_INTERNAL_URL = "http://localhost:3456";
  ({ resolveBackendOrigin } = await import("./backendOrigin"));
});

afterAll(() => {
  if (originalBackendInternalUrl === undefined) {
    delete process.env.BACKEND_INTERNAL_URL;
  } else {
    process.env.BACKEND_INTERNAL_URL = originalBackendInternalUrl;
  }
});

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

  it("fails loud when no backend URL is configured", () => {
    expect(() => resolveBackendOrigin({} as NodeJS.ProcessEnv)).toThrow(
      "Set BACKEND_INTERNAL_URL or NEXT_PUBLIC_API_URL",
    );
  });
});
