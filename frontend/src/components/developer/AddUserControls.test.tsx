import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

async function openForm() {
  await userEvent.click(screen.getByLabelText("User actions"));
  await userEvent.click(await screen.findByText("Add a user"));
  return screen.getByPlaceholderText("user_id (e.g. org_acme)");
}

describe("AddUserControls", () => {
  it("keeps the form behind the menu until asked for", () => {
    render(<AddUserControls onAdded={() => {}} />);
    expect(screen.queryByPlaceholderText("user_id (e.g. org_acme)")).not.toBeInTheDocument();
    expect(screen.getByLabelText("User actions")).toBeInTheDocument();
  });

  it("creates a user from the typed user_id and optional name, then closes", async () => {
    createUser.mockResolvedValue({});
    const onAdded = vi.fn();
    render(<AddUserControls onAdded={onAdded} />);

    fireEvent.change(await openForm(), { target: { value: "  org_acme  " } });
    fireEvent.change(screen.getByPlaceholderText(/Name \(optional/), {
      target: { value: "Acme Fleet Services" },
    });
    fireEvent.click(screen.getByText("Add user"));

    await waitFor(() => {
      expect(createUser).toHaveBeenCalledWith("org_acme", "Acme Fleet Services");
    });
    expect(onAdded).toHaveBeenCalledOnce();
    // Success collapses back to the menu; the next open starts blank.
    expect(screen.queryByPlaceholderText("user_id (e.g. org_acme)")).not.toBeInTheDocument();
  });

  it("omits the name when left blank", async () => {
    createUser.mockResolvedValue({});
    render(<AddUserControls onAdded={() => {}} />);

    fireEvent.change(await openForm(), { target: { value: "org_solo" } });
    fireEvent.click(screen.getByText("Add user"));

    await waitFor(() => {
      expect(createUser).toHaveBeenCalledWith("org_solo", undefined);
    });
  });

  it("shows the server error and keeps the form open for correction", async () => {
    createUser.mockRejectedValue(new Error("user 'org_dup' already exists"));
    const onAdded = vi.fn();
    render(<AddUserControls onAdded={onAdded} />);

    fireEvent.change(await openForm(), { target: { value: "org_dup" } });
    fireEvent.click(screen.getByText("Add user"));

    expect(await screen.findByText("user 'org_dup' already exists")).toBeTruthy();
    expect(screen.getByPlaceholderText("user_id (e.g. org_acme)")).toHaveValue("org_dup");
    expect(onAdded).not.toHaveBeenCalled();
  });

  it("disables submission until a user_id is typed", async () => {
    render(<AddUserControls onAdded={() => {}} />);
    await openForm();
    expect(screen.getByText("Add user")).toBeDisabled();
  });

  it("closes from the X without creating anything", async () => {
    render(<AddUserControls onAdded={() => {}} />);
    await openForm();
    await userEvent.click(screen.getByLabelText("Close"));
    expect(screen.queryByPlaceholderText("user_id (e.g. org_acme)")).not.toBeInTheDocument();
    expect(createUser).not.toHaveBeenCalled();
  });
});
