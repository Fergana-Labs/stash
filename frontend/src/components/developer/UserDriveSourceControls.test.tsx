import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import UserDriveSourceControls from "./UserDriveSourceControls";

const addSource = vi.fn();
const listIntegrations = vi.fn();

vi.mock("@/lib/api", () => ({
  addSource: (...args: unknown[]) => addSource(...args),
}));

vi.mock("@/lib/integrations", () => ({
  listIntegrations: () => listIntegrations(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("UserDriveSourceControls", () => {
  it("assigns one Drive folder to the selected external user", async () => {
    listIntegrations.mockResolvedValue({
      providers: [{ provider: "google", enabled: true, connected: true }],
    });
    addSource.mockResolvedValue({});
    const onAdded = vi.fn();
    render(<UserDriveSourceControls externalUserId="org_acme" onAdded={onAdded} />);

    fireEvent.change(await screen.findByPlaceholderText("Paste a Drive folder link"), {
      target: { value: "https://drive.google.com/drive/folders/1AbC_dEf-234567890" },
    });
    fireEvent.change(screen.getByPlaceholderText(/Name \(optional/), {
      target: { value: "Acme fleet records" },
    });
    fireEvent.click(screen.getByText("Add folder"));

    await waitFor(() => {
      expect(addSource).toHaveBeenCalledWith({
        source_type: "google_drive_folder",
        external_ref: "1AbC_dEf-234567890",
        display_name: "Acme fleet records",
        user_id: "org_acme",
      });
    });
    expect(onAdded).toHaveBeenCalledOnce();
    expect(screen.queryByText("Add My Drive")).not.toBeInTheDocument();
  });

  it("sends the user to connect Google Drive before assigning a folder", async () => {
    listIntegrations.mockResolvedValue({
      providers: [{ provider: "google", enabled: true, connected: false }],
    });
    render(<UserDriveSourceControls externalUserId="org_acme" onAdded={() => {}} />);

    const link = await screen.findByRole("link", { name: "Connect Google Drive" });
    expect(link).toHaveAttribute("href", "/integrations/google");
    expect(screen.queryByPlaceholderText("Paste a Drive folder link")).not.toBeInTheDocument();
  });

  it("keeps the folder form available when assignment fails", async () => {
    listIntegrations.mockResolvedValue({
      providers: [{ provider: "google", enabled: true, connected: true }],
    });
    addSource.mockRejectedValue(new Error("This Google account cannot read that folder."));
    render(<UserDriveSourceControls externalUserId="org_acme" onAdded={() => {}} />);

    fireEvent.change(await screen.findByPlaceholderText("Paste a Drive folder link"), {
      target: { value: "https://drive.google.com/drive/folders/1AbC_dEf-234567890" },
    });
    fireEvent.click(screen.getByText("Add folder"));

    expect(await screen.findByText("This Google account cannot read that folder.")).toBeTruthy();
    expect(screen.getByPlaceholderText("Paste a Drive folder link")).toBeTruthy();
  });
});
