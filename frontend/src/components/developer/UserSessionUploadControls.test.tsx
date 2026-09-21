import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import UserSessionUploadControls from "./UserSessionUploadControls";

const uploadTranscript = vi.fn();

vi.mock("@/lib/api", () => ({
  uploadTranscript: (...args: unknown[]) => uploadTranscript(...args),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

async function openForm() {
  await userEvent.click(screen.getByLabelText("Session actions"));
  await userEvent.click(await screen.findByText("Upload a session transcript"));
}

const transcript = new File(['{"type":"user"}\n'], "sess-support-42.jsonl");

describe("UserSessionUploadControls", () => {
  it("keeps the form behind the menu until asked for", () => {
    render(<UserSessionUploadControls externalUserId="org_acme" onAdded={() => {}} />);
    expect(screen.queryByPlaceholderText("Session id")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Session actions")).toBeInTheDocument();
  });

  it("uploads the transcript under the user, prefilled from the filename", async () => {
    uploadTranscript.mockResolvedValue({ session_id: "sess-support-42", imported: 2, skipped: false });
    const onAdded = vi.fn();
    render(<UserSessionUploadControls externalUserId="org_acme" onAdded={onAdded} />);

    await openForm();
    fireEvent.change(screen.getByTestId("user-transcript-input"), {
      target: { files: [transcript] },
    });
    // The filename stem lands in the session id field.
    expect(screen.getByPlaceholderText("Session id")).toHaveValue("sess-support-42");
    fireEvent.change(screen.getByPlaceholderText(/Agent name/), {
      target: { value: "support-bot" },
    });
    fireEvent.click(screen.getByText("Upload"));

    await waitFor(() => {
      expect(uploadTranscript).toHaveBeenCalledWith(
        transcript,
        "sess-support-42",
        "support-bot",
        undefined,
        "org_acme",
      );
    });
    expect(onAdded).toHaveBeenCalledOnce();
    expect(screen.queryByPlaceholderText("Session id")).not.toBeInTheDocument();
  });

  it("surfaces a skipped upload instead of pretending it imported", async () => {
    uploadTranscript.mockResolvedValue({
      session_id: "sess-support-42",
      imported: 0,
      skipped: true,
      reason: "session already has events",
    });
    const onAdded = vi.fn();
    render(<UserSessionUploadControls externalUserId="org_acme" onAdded={onAdded} />);

    await openForm();
    fireEvent.change(screen.getByTestId("user-transcript-input"), {
      target: { files: [transcript] },
    });
    fireEvent.change(screen.getByPlaceholderText(/Agent name/), { target: { value: "bot" } });
    fireEvent.click(screen.getByText("Upload"));

    expect(
      await screen.findByText("Nothing imported: session already has events."),
    ).toBeTruthy();
    expect(onAdded).not.toHaveBeenCalled();
  });

  it("shows the server error and keeps the form open", async () => {
    uploadTranscript.mockRejectedValue(
      new Error("session 'sess-support-42' already belongs to org_beta"),
    );
    render(<UserSessionUploadControls externalUserId="org_acme" onAdded={() => {}} />);

    await openForm();
    fireEvent.change(screen.getByTestId("user-transcript-input"), {
      target: { files: [transcript] },
    });
    fireEvent.change(screen.getByPlaceholderText(/Agent name/), { target: { value: "bot" } });
    fireEvent.click(screen.getByText("Upload"));

    expect(
      await screen.findByText("session 'sess-support-42' already belongs to org_beta"),
    ).toBeTruthy();
    expect(screen.getByPlaceholderText("Session id")).toHaveValue("sess-support-42");
  });

  it("disables the upload until a file, session id, and agent name are set", async () => {
    render(<UserSessionUploadControls externalUserId="org_acme" onAdded={() => {}} />);
    await openForm();
    expect(screen.getByText("Upload")).toBeDisabled();
    fireEvent.change(screen.getByTestId("user-transcript-input"), {
      target: { files: [transcript] },
    });
    expect(screen.getByText("Upload")).toBeDisabled();
    fireEvent.change(screen.getByPlaceholderText(/Agent name/), { target: { value: "bot" } });
    expect(screen.getByText("Upload")).toBeEnabled();
  });
});
