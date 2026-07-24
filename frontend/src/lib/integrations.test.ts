import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./api", () => ({ apiFetch: vi.fn() }));

import { apiFetch } from "./api";
import {
  INTEGRATIONS_CHANGED_EVENT,
  disconnectIntegration,
  submitCredentials,
} from "./integrations";

// Status surfaces that stay mounted across a disconnect (the sidebar Tools
// list) rely on this event to drop their "Connected" badge immediately —
// without it the stale badge lingers until the surface remounts.
describe("integrations-changed event", () => {
  let fired: number;
  const onChanged = () => fired++;
  beforeEach(() => {
    fired = 0;
    vi.mocked(apiFetch).mockReset();
    window.addEventListener(INTEGRATIONS_CHANGED_EVENT, onChanged);
  });
  afterEach(() => {
    window.removeEventListener(INTEGRATIONS_CHANGED_EVENT, onChanged);
  });

  it("fires after a successful disconnect", async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined);
    await disconnectIntegration("github");
    expect(fired).toBe(1);
  });

  it("does not fire when disconnect fails", async () => {
    vi.mocked(apiFetch).mockRejectedValue(new Error("boom"));
    await expect(disconnectIntegration("github")).rejects.toThrow("boom");
    expect(fired).toBe(0);
  });

  it("fires after a successful credential connect", async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined);
    await submitCredentials("gong", { api_key: "k" });
    expect(fired).toBe(1);
  });
});
