import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { submitContactSales } from "./actions";

const fetchMock = vi.fn();
const validResult = { success: true, hostname: "www.joinstash.ai", action: "contact_sales" };

function form(token: string | null = "valid-token") {
  const data = new FormData();
  data.set("name", "Demo Visitor");
  data.set("email", "visitor@example.com");
  if (token !== null) data.set("cf-turnstile-response", token);
  return data;
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("TURNSTILE_SECRET_KEY", "test-secret");
  vi.stubEnv("TURNSTILE_HOSTNAME", "www.joinstash.ai");
  vi.stubEnv("POSTMARK_SERVER_TOKEN", "test-postmark-token");
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  fetchMock.mockReset();
});

test.each([null, "", "x".repeat(2049)])("rejects missing or malformed tokens without sending email (%#)", async (token) => {
  expect((await submitContactSales({ status: "idle" }, form(token))).status).toBe("error");
  expect(fetchMock).not.toHaveBeenCalled();
});

test.each([
  { success: false, "error-codes": ["invalid-input-response"] },
  { success: false, "error-codes": ["timeout-or-duplicate"] },
  { ...validResult, hostname: "another-site.example" },
  { ...validResult, action: "another_form" },
  {},
])("sends no emails when verification is rejected: %j", async (result) => {
  fetchMock.mockResolvedValueOnce(Response.json(result));
  expect((await submitContactSales({ status: "idle" }, form())).status).toBe("error");
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls[0][0]).toBe("https://challenges.cloudflare.com/turnstile/v0/siteverify");
});

test.each(["TURNSTILE_SECRET_KEY", "TURNSTILE_HOSTNAME"])("missing %s blocks email delivery", async (key) => {
  vi.stubEnv(key, "");
  expect((await submitContactSales({ status: "idle" }, form())).status).toBe("error");
  expect(fetchMock).not.toHaveBeenCalled();
});

test.each(["network", "http", "json"])("verification %s failures block both emails", async (failure) => {
  if (failure === "network") fetchMock.mockRejectedValueOnce(new Error("network unavailable"));
  if (failure === "http") fetchMock.mockResolvedValueOnce(new Response("unavailable", { status: 503 }));
  if (failure === "json") fetchMock.mockResolvedValueOnce(new Response("invalid json"));
  expect((await submitContactSales({ status: "idle" }, form())).status).toBe("error");
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("sends Sam's lead and the visitor's confirmation only after verification succeeds", async () => {
  fetchMock.mockResolvedValueOnce(Response.json(validResult));
  fetchMock.mockImplementation(async () => Response.json({ ErrorCode: 0 }));
  expect((await submitContactSales({ status: "idle" }, form())).status).toBe("ok");
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ secret: "test-secret", response: "valid-token" });
  expect(fetchMock.mock.calls.slice(1).map(([url, options]) => [url, JSON.parse(options.body).To])).toEqual([
    ["https://api.postmarkapp.com/email", "sam@joinstash.ai"],
    ["https://api.postmarkapp.com/email", "visitor@example.com"],
  ]);
});
