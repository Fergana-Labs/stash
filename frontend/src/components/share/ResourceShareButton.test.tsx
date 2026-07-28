import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ResourceShareButton from "./ResourceShareButton";
import {
  ApiError,
  getObjectAccess,
  shareObjectByEmail,
  unshareObject,
  updateGeneralAccess,
  type ObjectAccess,
  type ObjectShare,
} from "../../lib/api";

vi.mock("../../lib/api", async () => ({
  ...(await vi.importActual<typeof import("../../lib/api")>("../../lib/api")),
  getObjectAccess: vi.fn(),
  shareObjectByEmail: vi.fn(),
  unshareObject: vi.fn(),
  updateGeneralAccess: vi.fn(),
}));

const owner = {
  user_id: "user-1",
  label: "Henry Dowling",
  email: "henry@example.com",
  is_you: true,
};

const adaShare: ObjectShare = {
  principal_type: "user",
  principal_id: "user-2",
  label: "Ada Lovelace",
  email: "ada@example.com",
  permission: "read",
  pending: false,
};

function access(overrides: Partial<ObjectAccess> = {}): ObjectAccess {
  return { owner, shares: [adaShare], general_access: "none", ...overrides };
}

describe("ResourceShareButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    vi.mocked(getObjectAccess).mockResolvedValue(access());
    vi.mocked(shareObjectByEmail).mockResolvedValue(undefined);
    vi.mocked(unshareObject).mockResolvedValue(undefined);
    vi.mocked(updateGeneralAccess).mockImplementation(
      async (_type, _id, permission) => permission,
    );
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
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Share" }));

    expect(
      await screen.findByRole("dialog", { name: "Share launch.png" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Henry Dowling (you)")).toBeInTheDocument();
    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("Restricted")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Copy link" }));

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      `${window.location.origin}/f/file-1`,
    );
    expect(await screen.findByText("Link copied.")).toBeInTheDocument();
  });

  it("shows the true owner, not the viewer, when they differ", async () => {
    // Workspace content is owned by the workspace's scope user; the dialog
    // must render that owner instead of assuming the logged-in user owns it.
    vi.mocked(getObjectAccess).mockResolvedValue(
      access({
        owner: {
          user_id: "ws-1",
          label: "Fergana Labs",
          email: null,
          is_you: false,
        },
      }),
    );

    render(
      <ResourceShareButton
        objectType="page"
        objectId="page-1"
        resourceName="Org page"
        resourceUrlPath="/p/page-1"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Share" }));

    expect(await screen.findByText("Fergana Labs")).toBeInTheDocument();
    expect(screen.getByText("Workspace")).toBeInTheDocument();
    expect(screen.queryByText(/\(you\)/)).toBeNull();
  });

  it("explains instead of offering controls when the viewer cannot share", async () => {
    // A share/public-link recipient can open the dialog but the access
    // listing 404s; dead invite controls must not render.
    vi.mocked(getObjectAccess).mockRejectedValue(new ApiError(404, "Not found"));

    render(
      <ResourceShareButton
        objectType="page"
        objectId="page-1"
        resourceName="Someone else's page"
        resourceUrlPath="/p/page-1"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Share" }));

    expect(
      await screen.findByText(
        "You can view this item, but only its owner can manage sharing.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Add people")).toBeNull();
    expect(screen.queryByText("General access")).toBeNull();
  });

  it("invites people directly to the resource", async () => {
    vi.mocked(getObjectAccess)
      .mockResolvedValueOnce(access({ shares: [] }))
      .mockResolvedValueOnce(
        access({
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
        }),
      );

    render(
      <ResourceShareButton
        objectType="table"
        objectId="table-1"
        resourceName="Prospects"
        resourceUrlPath="/tables/table-1"
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

  it("changes an existing person's permission", async () => {
    render(
      <ResourceShareButton
        objectType="page"
        objectId="page-1"
        resourceName="Blog post outline"
        resourceUrlPath="/p/page-1"
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

  it("shares a source read-only: no permission choices, invites at read", async () => {
    // The backend rejects comment/write for sources, so the dialog must not
    // offer a level to pick and must send read — otherwise the POST 400s.
    render(
      <ResourceShareButton
        objectType="source"
        objectId="src-1"
        resourceName="Team Drive"
        resourceUrlPath="/integrations/google?source=src-1"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Share" }));
    await screen.findByRole("dialog", { name: "Share Team Drive" });
    await screen.findByText("Ada Lovelace");

    expect(screen.queryByLabelText("Invite permission")).toBeNull();
    expect(screen.queryByLabelText("Change permission")).toBeNull();

    fireEvent.change(screen.getByLabelText("Add people"), {
      target: { value: "grace@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Invite" }));

    await waitFor(() =>
      expect(shareObjectByEmail).toHaveBeenCalledWith(
        "source",
        "src-1",
        "grace@example.com",
        "read",
      ),
    );
  });
});
