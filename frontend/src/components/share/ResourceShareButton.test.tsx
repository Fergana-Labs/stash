import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ResourceShareButton from "./ResourceShareButton";
import {
  listObjectShares,
  setGeneralAccess,
  shareObjectByEmail,
  unshareObject,
} from "../../lib/api";

vi.mock("../../lib/api", () => ({
  listObjectShares: vi.fn(),
  setGeneralAccess: vi.fn(),
  shareObjectByEmail: vi.fn(),
  unshareObject: vi.fn(),
}));

const currentUser = {
  id: "user-1",
  name: "henry",
  display_name: "Henry Dowling",
  email: "henry@example.com",
  description: "",
  created_at: "2026-05-11T00:00:00Z",
  last_seen: "2026-05-11T00:00:00Z",
};

describe("ResourceShareButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    vi.mocked(listObjectShares).mockResolvedValue({
      shares: [
        {
          principal_type: "user",
          principal_id: "user-2",
          label: "Ada Lovelace",
          email: "ada@example.com",
          permission: "read",
          pending: false,
        },
      ],
      general_access: "restricted",
    });
    vi.mocked(setGeneralAccess).mockResolvedValue(undefined);
    vi.mocked(shareObjectByEmail).mockResolvedValue(undefined);
    vi.mocked(unshareObject).mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
  });

  it("shows file access and copies the canonical file URL", async () => {
    render(
      <ResourceShareButton
        objectType="file"
        objectId="file-1"
        resourceName="launch.png"
        resourceUrlPath="/f/file-1"
        currentUser={currentUser}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Share" }));

    expect(
      await screen.findByRole("dialog", { name: "Share launch.png" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Henry Dowling (you)")).toBeInTheDocument();
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("Restricted")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Copy link" }));

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      `${window.location.origin}/f/file-1`,
    );
    expect(await screen.findByText("Link copied.")).toBeInTheDocument();
  });

  it("invites people directly to the resource", async () => {
    vi.mocked(listObjectShares)
      .mockResolvedValueOnce({ shares: [], general_access: "restricted" })
      .mockResolvedValueOnce({
        shares: [
          {
            principal_type: "user",
            principal_id: null,
            label: "ada@example.com",
            email: "ada@example.com",
            permission: "write",
            pending: true,
          },
        ],
        general_access: "restricted",
      });

    render(
      <ResourceShareButton
        objectType="table"
        objectId="table-1"
        resourceName="Prospects"
        resourceUrlPath="/tables/table-1"
        currentUser={currentUser}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Share" }));
    await screen.findByRole("dialog", { name: "Share Prospects" });

    fireEvent.change(screen.getByLabelText("Add people"), {
      target: { value: "ada@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Invite permission"), {
      target: { value: "write" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Invite" }));

    await waitFor(() =>
      expect(shareObjectByEmail).toHaveBeenCalledWith(
        "table",
        "table-1",
        "ada@example.com",
        "write",
      ),
    );
    expect(await screen.findByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText("Invited")).toBeInTheDocument();
  });

  it("makes the resource public via the general-access select", async () => {
    render(
      <ResourceShareButton
        objectType="page"
        objectId="page-1"
        resourceName="Blog post outline"
        resourceUrlPath="/p/page-1"
        currentUser={currentUser}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Share" }));
    const select = await screen.findByLabelText("General access");
    expect(select).toHaveValue("restricted");

    fireEvent.change(select, { target: { value: "public" } });

    await waitFor(() =>
      expect(setGeneralAccess).toHaveBeenCalledWith("page", "page-1", "public"),
    );
    expect(await screen.findByText("Access updated.")).toBeInTheDocument();
    expect(select).toHaveValue("public");
  });

  it("changes an existing person's permission", async () => {
    render(
      <ResourceShareButton
        objectType="page"
        objectId="page-1"
        resourceName="Blog post outline"
        resourceUrlPath="/p/page-1"
        currentUser={currentUser}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Share" }));
    await screen.findByText("Ada Lovelace");

    fireEvent.change(screen.getByLabelText("Change permission"), {
      target: { value: "comment" },
    });

    await waitFor(() =>
      expect(shareObjectByEmail).toHaveBeenCalledWith(
        "page",
        "page-1",
        "ada@example.com",
        "comment",
      ),
    );
    expect(await screen.findByText("Access updated.")).toBeInTheDocument();
  });
});
