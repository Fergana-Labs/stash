import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import UserFileUploadControls from "./UserFileUploadControls";

const uploadFile = vi.fn();

vi.mock("@/lib/api", () => ({
  uploadFile: (...args: unknown[]) => uploadFile(...args),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("UserFileUploadControls", () => {
  it("uploads the picked file scoped to the user", async () => {
    uploadFile.mockResolvedValue({});
    const onAdded = vi.fn();
    render(<UserFileUploadControls externalUserId="org_acme" onAdded={onAdded} />);

    const file = new File(["%PDF-1.4"], "coverage.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByTestId("user-file-input"), { target: { files: [file] } });

    await waitFor(() => {
      expect(uploadFile).toHaveBeenCalledWith(file, null, "org_acme");
    });
    expect(onAdded).toHaveBeenCalledOnce();
  });

  it("shows the server error and stays usable", async () => {
    uploadFile.mockRejectedValue(new Error("File too large (max 100 MB)"));
    const onAdded = vi.fn();
    render(<UserFileUploadControls externalUserId="org_acme" onAdded={onAdded} />);

    const file = new File(["x"], "huge.bin");
    fireEvent.change(screen.getByTestId("user-file-input"), { target: { files: [file] } });

    expect(await screen.findByText("File too large (max 100 MB)")).toBeTruthy();
    expect(screen.getByText("Upload a file")).toBeEnabled();
    expect(onAdded).not.toHaveBeenCalled();
  });
});
