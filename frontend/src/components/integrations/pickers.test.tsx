import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../lib/api";
import type { Connector } from "./connectors";
import { AddSourceControls } from "./pickers";

const addSource = vi.fn();

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    addSource: (...args: unknown[]) => addSource(...args),
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
    <AddSourceControls connector={driveConnector} connected onAdded={() => {}} />
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// Adding sources under a connection is unlimited — the pay gate lives on the
// connect step, not here. A failed add just surfaces the backend error inline.
describe("AddSourceControls", () => {
  it("surfaces the backend error inline, with no paywall", async () => {
    addSource.mockRejectedValue(new ApiError(400, "external_ref is required"));
    renderControls();

    fireEvent.click(screen.getByText("Add My Drive"));

    expect(await screen.findByText("external_ref is required")).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
