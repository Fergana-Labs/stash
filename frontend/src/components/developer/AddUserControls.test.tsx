import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AddUserControls from "./AddUserControls";

const createUser = vi.fn();

vi.mock("@/lib/api", () => ({
  createUser: (...args: unknown[]) => createUser(...args),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AddUserControls", () => {
  it("creates a user from the typed user_id and optional name", async () => {
    createUser.mockResolvedValue({});
    const onAdded = vi.fn();
    render(<AddUserControls onAdded={onAdded} />);

    fireEvent.change(screen.getByPlaceholderText("user_id (e.g. org_acme)"), {
      target: { value: "  org_acme  " },
    });
    fireEvent.change(screen.getByPlaceholderText(/Name \(optional/), {
      target: { value: "Acme Fleet Services" },
    });
    fireEvent.click(screen.getByText("Add user"));

    await waitFor(() => {
      expect(createUser).toHaveBeenCalledWith("org_acme", "Acme Fleet Services");
    });
    expect(onAdded).toHaveBeenCalledOnce();
    expect(screen.getByPlaceholderText("user_id (e.g. org_acme)")).toHaveValue("");
  });

  it("omits the name when left blank", async () => {
    createUser.mockResolvedValue({});
    render(<AddUserControls onAdded={() => {}} />);

    fireEvent.change(screen.getByPlaceholderText("user_id (e.g. org_acme)"), {
      target: { value: "org_solo" },
    });
    fireEvent.click(screen.getByText("Add user"));

    await waitFor(() => {
      expect(createUser).toHaveBeenCalledWith("org_solo", undefined);
    });
  });

  it("shows the server error and keeps the typed user_id for correction", async () => {
    createUser.mockRejectedValue(new Error("user 'org_dup' already exists"));
    const onAdded = vi.fn();
    render(<AddUserControls onAdded={onAdded} />);

    fireEvent.change(screen.getByPlaceholderText("user_id (e.g. org_acme)"), {
      target: { value: "org_dup" },
    });
    fireEvent.click(screen.getByText("Add user"));

    expect(await screen.findByText("user 'org_dup' already exists")).toBeTruthy();
    expect(screen.getByPlaceholderText("user_id (e.g. org_acme)")).toHaveValue("org_dup");
    expect(onAdded).not.toHaveBeenCalled();
  });

  it("disables submission until a user_id is typed", () => {
    render(<AddUserControls onAdded={() => {}} />);
    expect(screen.getByText("Add user")).toBeDisabled();
  });
});
