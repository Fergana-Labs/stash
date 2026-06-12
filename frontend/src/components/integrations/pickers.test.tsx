import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../lib/api";
import type { Connector } from "./connectors";
import { AddSourceControls } from "./pickers";

const addWorkspaceSource = vi.fn();
const startCheckout = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    addWorkspaceSource: (...args: unknown[]) => addWorkspaceSource(...args),
    startCheckout: (...args: unknown[]) => startCheckout(...args),
  };
});

const driveConnector: Connector = {
  provider: "google",
  label: "Google Drive",
  sourceType: "google_drive",
  kind: "drive",
  blurb: "",
};

function renderControls() {
  return render(
    <AddSourceControls
      connector={driveConnector}
      workspaceId="ws-1"
      connected
      onAdded={() => {}}
    />
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// The free plan allows 1 connected source; the backend rejects further adds
// with 402. The user must see the paywall (not just an error) so the upgrade
// path is one click away.
describe("AddSourceControls pay gate", () => {
  it("shows the paywall modal when the backend returns 402", async () => {
    addWorkspaceSource.mockRejectedValue(
      new ApiError(402, "The free plan includes 1 connected source. Upgrade to Pro to connect more.")
    );
    renderControls();

    fireEvent.click(screen.getByText("Add My Drive"));

    expect(await screen.findByRole("dialog", { name: "Upgrade to Pro" })).toBeTruthy();
    expect(addWorkspaceSource).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByText("Not now"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("does not show the paywall for other errors", async () => {
    addWorkspaceSource.mockRejectedValue(new ApiError(400, "external_ref is required"));
    renderControls();

    fireEvent.click(screen.getByText("Add My Drive"));

    expect(await screen.findByText("external_ref is required")).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("starts checkout from the paywall modal", async () => {
    addWorkspaceSource.mockRejectedValue(new ApiError(402, "Upgrade to Pro to connect more."));
    startCheckout.mockReturnValue(new Promise(() => {})); // redirect never settles in tests
    renderControls();

    fireEvent.click(screen.getByText("Add My Drive"));
    fireEvent.click(await screen.findByText("Upgrade — $20/month"));

    expect(startCheckout).toHaveBeenCalledOnce();
  });
});
