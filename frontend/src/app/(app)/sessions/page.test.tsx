import {
  cleanup,
  fireEvent,
  render as renderBase,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SessionsPage from "./page";
import {
  assignSessionsToFolder,
  createSessionFolder,
  deleteSession,
  deleteSessionFolder,
  listMySessions,
  listSessionFolders,
  renameSessionFolder,
  type SessionFolder,
  type SessionSummary,
} from "@/lib/api";
import { usePins } from "@/lib/pins";
import { ConfirmDialogProvider } from "@/components/ConfirmDialog";

function render(ui: ReactNode) {
  return renderBase(ui, { wrapper: ConfirmDialogProvider });
}

const router = vi.hoisted(() => ({
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: ReactNode;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/api", () => ({
  assignSessionsToFolder: vi.fn(),
  createSessionFolder: vi.fn(),
  deleteSession: vi.fn(),
  deleteSessionFolder: vi.fn(),
  listMySessions: vi.fn(),
  listSessionFolders: vi.fn(),
  renameSessionFolder: vi.fn(),
}));

vi.mock("@/lib/pins", () => ({
  usePins: vi.fn(() => ({
    pinnedIds: [],
    pinnedSet: new Set<string>(),
    isPinned: () => false,
    toggle: vi.fn(),
  })),
}));

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({
    user: { id: "user-1", name: "sam", display_name: "Sam" },
    loading: false,
  }),
}));

vi.mock("@/components/BreadcrumbContext", () => ({
  useBreadcrumbs: () => {},
}));

vi.mock("@/components/SessionUpload", () => ({
  default: () => null,
}));

function session(overrides: Partial<SessionSummary> = {}): SessionSummary {
  return {
    session_id: "sess-1",
    id: "row-1",
    title: "First session",
    linear_tickets: [],
    owner_user_id: "user-1",
    user_name: "sam",
    agent_name: "claude-code",
    session_folder_name: null,
    event_count: 5,
    started_at: "2026-08-01T10:00:00Z",
    last_event_at: "2026-08-01T12:00:00Z",
    ...overrides,
  };
}

function folder(overrides: Partial<SessionFolder> = {}): SessionFolder {
  return {
    id: "f-1",
    slug: "folder-1",
    name: "Work",
    access: "private",
    discoverable: false,
    is_default: false,
    session_count: 0,
    share_count: 0,
    ...overrides,
  };
}

const defaultFolder = () =>
  folder({ id: "f-default", slug: "default", name: "Default", is_default: true });

describe("SessionsPage folders", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    router.push.mockReset();
    vi.mocked(usePins).mockReturnValue({
      pinnedIds: [],
      pinnedSet: new Set<string>(),
      isPinned: () => false,
      toggle: vi.fn(),
    });
    vi.mocked(listMySessions).mockResolvedValue([]);
    vi.mocked(listSessionFolders).mockResolvedValue([]);
    vi.mocked(assignSessionsToFolder).mockResolvedValue({ ok: true, moved: 1 });
    vi.mocked(createSessionFolder).mockResolvedValue(folder({}));
    vi.mocked(renameSessionFolder).mockResolvedValue(folder({}));
    vi.mocked(deleteSessionFolder).mockResolvedValue(undefined);
    vi.mocked(deleteSession).mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  async function openFoldersPanel() {
    fireEvent.click(await screen.findByRole("button", { name: "Folders" }));
  }

  it("lists folders with markers and counts when the panel opens", async () => {
    vi.mocked(listMySessions).mockResolvedValue([
      session({ session_folder_name: "Work" }),
    ]);
    vi.mocked(listSessionFolders).mockResolvedValue([
      defaultFolder(),
      folder({
        id: "f-work",
        slug: "work",
        name: "Work",
        access: "public",
        discoverable: true,
        session_count: 3,
      }),
    ]);
    render(<SessionsPage />);

    expect(await screen.findByText("First session")).toBeInTheDocument();

    const foldersButton = screen.getByRole("button", { name: "Folders" });
    expect(foldersButton).toHaveAttribute("aria-expanded", "false");
    await openFoldersPanel();
    expect(foldersButton).toHaveAttribute("aria-expanded", "true");

    expect(screen.getByText("Session folders")).toBeInTheDocument();
    // "Work" appears in the table's Folder column and the panel row.
    expect(screen.getAllByText("Work").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/3 sessions/)).toBeInTheDocument();
    // The default folder ships named "Default" — the name IS the marker, so
    // the row carries no duplicate chip.
    expect(screen.getByText("Default")).toBeInTheDocument();
    expect(screen.getByText("Public")).toBeInTheDocument();
    expect(screen.getByText("Discoverable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New folder" })).toBeInTheDocument();
  });

  it("creates a folder from the prompt and re-fetches the folder list", async () => {
    vi.spyOn(window, "prompt").mockReturnValue("Ideas");
    vi.mocked(listSessionFolders)
      .mockResolvedValueOnce([defaultFolder()])
      .mockResolvedValue([folder({ id: "f-ideas", name: "Ideas" }), defaultFolder()]);

    render(<SessionsPage />);
    await openFoldersPanel();
    fireEvent.click(screen.getByRole("button", { name: "New folder" }));

    expect(window.prompt).toHaveBeenCalledWith("Folder name?");
    expect(createSessionFolder).toHaveBeenCalledTimes(1);
    expect(createSessionFolder).toHaveBeenCalledWith("Ideas");
    await waitFor(() => expect(listSessionFolders).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Ideas")).toBeInTheDocument();
  });

  it("makes no API call when the create prompt answer is blank", async () => {
    vi.spyOn(window, "prompt").mockReturnValue("   ");

    render(<SessionsPage />);
    await openFoldersPanel();
    fireEvent.click(screen.getByRole("button", { name: "New folder" }));

    expect(window.prompt).toHaveBeenCalled();
    expect(createSessionFolder).not.toHaveBeenCalled();
    expect(listSessionFolders).toHaveBeenCalledTimes(1);
  });

  it("renames a folder from the prompt and refreshes sessions and folders", async () => {
    vi.spyOn(window, "prompt").mockReturnValue("Projects");
    vi.mocked(listMySessions).mockResolvedValue([
      session({ session_folder_name: "Work" }),
    ]);
    vi.mocked(listSessionFolders)
      .mockResolvedValueOnce([folder({ id: "f-work", slug: "work", name: "Work" })])
      .mockResolvedValue([
        folder({ id: "f-work", slug: "work", name: "Projects" }),
      ]);

    render(<SessionsPage />);
    await openFoldersPanel();
    fireEvent.click(screen.getByRole("button", { name: "Rename" }));

    expect(window.prompt).toHaveBeenCalledWith("Folder name:", "Work");
    await waitFor(() =>
      expect(renameSessionFolder).toHaveBeenCalledWith("f-work", "Projects"),
    );
    // The Folder column shows the new name, so the session list re-fetches.
    await waitFor(() => expect(listMySessions).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(listSessionFolders).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("Projects")).toBeInTheDocument();
  });

  it("deletes a folder after the confirm dialog is confirmed", async () => {
    vi.mocked(listSessionFolders).mockResolvedValue([
      folder({ id: "f-work", slug: "work", name: "Work" }),
    ]);

    render(<SessionsPage />);
    await openFoldersPanel();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveAttribute("aria-label", 'Delete folder "Work"?');
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() =>
      expect(deleteSessionFolder).toHaveBeenCalledWith("f-work"),
    );
    await waitFor(() => expect(listMySessions).toHaveBeenCalledTimes(2));
  });

  it("does not delete when the confirm dialog is cancelled", async () => {
    vi.mocked(listSessionFolders).mockResolvedValue([
      folder({ id: "f-work", slug: "work", name: "Work" }),
    ]);

    render(<SessionsPage />);
    await openFoldersPanel();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));

    expect(deleteSessionFolder).not.toHaveBeenCalled();
  });

  it("hides Delete (but keeps Rename) on the Default folder row", async () => {
    vi.mocked(listSessionFolders).mockResolvedValue([
      // Renamed default: the "Default" chip must appear next to the name.
      folder({ id: "f-default", slug: "default", name: "Home", is_default: true }),
      folder({ id: "f-work", slug: "work", name: "Work" }),
    ]);

    render(<SessionsPage />);
    await openFoldersPanel();

    expect(screen.getByText("Home")).toBeInTheDocument();
    expect(screen.getByText("Default")).toBeInTheDocument();
    // Only the non-Default row offers Delete.
    expect(screen.getAllByRole("button", { name: "Delete" }).length).toBe(1);
    expect(screen.getAllByRole("button", { name: "Rename" }).length).toBe(2);
  });

  it("shows the error banner when the folders fetch fails while sessions still render", async () => {
    vi.mocked(listMySessions).mockResolvedValue([
      session({ title: "Visible session" }),
    ]);
    vi.mocked(listSessionFolders).mockRejectedValue(new Error("Folders blew up"));

    render(<SessionsPage />);

    expect(await screen.findByText("Visible session")).toBeInTheDocument();
    expect(await screen.findByText("Folders blew up")).toBeInTheDocument();
  });

  it("renders the read-only Folder column for filed sessions", async () => {
    vi.mocked(listMySessions).mockResolvedValue([
      session({ session_folder_name: "Work" }),
    ]);

    render(<SessionsPage />);

    expect(await screen.findByText("First session")).toBeInTheDocument();
    expect(screen.getByText("Folder")).toBeInTheDocument();
    expect(screen.getByText("Work")).toBeInTheDocument();
  });

  async function selectRows(indices: number[]) {
    const boxes = await screen.findAllByRole("checkbox");
    for (const i of indices) fireEvent.click(boxes[i]);
  }

  it("moves selected sessions to a folder from the selection bar menu", async () => {
    // One pinned row (Pinned section) and one main-table row: selection is
    // page-level, so both checkboxes feed the same bar.
    vi.mocked(usePins).mockReturnValue({
      pinnedIds: ["sess-1"],
      pinnedSet: new Set(["sess-1"]),
      isPinned: (id: string) => id === "sess-1",
      toggle: vi.fn(),
    });
    vi.mocked(listMySessions).mockResolvedValue([
      session({ session_id: "sess-1", id: "row-1", last_event_at: "2026-08-01T12:00:00Z" }),
      session({ session_id: "sess-2", id: "row-2", title: "Second session", last_event_at: "2026-08-01T11:00:00Z" }),
    ]);
    vi.mocked(listSessionFolders).mockResolvedValue([
      folder({ id: "f-work", slug: "work", name: "Work", session_count: 3 }),
    ]);

    render(<SessionsPage />);
    // Checkboxes: [sess-1 pinned, sess-1 main, sess-2 main].
    await selectRows([0, 2]);

    expect(screen.getByText("2 selected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Move to folder" }));
    // The menu lists the folder and the Unfile entry.
    expect(screen.getByText("Unfile")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Work/ }));

    await waitFor(() =>
      expect(assignSessionsToFolder).toHaveBeenCalledTimes(1),
    );
    expect(assignSessionsToFolder).toHaveBeenCalledWith(
      ["row-1", "row-2"],
      "f-work",
    );
    // Selection clears and both lists re-fetch.
    await waitFor(() => expect(screen.queryByText("2 selected")).toBeNull());
    await waitFor(() => expect(listMySessions).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(listSessionFolders).toHaveBeenCalledTimes(2));
  });

  it("unfiles the selected session when the Unfile entry is picked", async () => {
    vi.mocked(listMySessions).mockResolvedValue([
      session({ session_id: "sess-1", id: "row-1" }),
    ]);
    vi.mocked(listSessionFolders).mockResolvedValue([
      folder({ id: "f-work", slug: "work", name: "Work" }),
    ]);

    render(<SessionsPage />);
    await selectRows([0]);
    expect(screen.getByText("1 selected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Move to folder" }));
    fireEvent.click(screen.getByRole("button", { name: "Unfile" }));

    await waitFor(() =>
      expect(assignSessionsToFolder).toHaveBeenCalledWith(["row-1"], null),
    );
  });

  it("excludes sessions without a row id from the assign payload", async () => {
    vi.mocked(listMySessions).mockResolvedValue([
      session({ session_id: "sess-1", id: "row-1" }),
      session({ session_id: "sess-2", id: null, title: "No row id" }),
    ]);
    vi.mocked(listSessionFolders).mockResolvedValue([
      folder({ id: "f-work", slug: "work", name: "Work" }),
    ]);

    render(<SessionsPage />);
    await selectRows([0, 1]);
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Move to folder" }));
    fireEvent.click(screen.getByRole("button", { name: /Work/ }));

    await waitFor(() =>
      expect(assignSessionsToFolder).toHaveBeenCalledWith(["row-1"], "f-work"),
    );
  });

  it("keeps the selection and shows the error banner when assign fails", async () => {
    vi.mocked(listMySessions).mockResolvedValue([
      session({ session_id: "sess-1", id: "row-1" }),
      session({ session_id: "sess-2", id: "row-2", title: "Second session" }),
    ]);
    vi.mocked(listSessionFolders).mockResolvedValue([
      folder({ id: "f-gone", slug: "gone", name: "Gone" }),
    ]);
    vi.mocked(assignSessionsToFolder).mockRejectedValue(
      new Error("Session or folder not found"),
    );

    render(<SessionsPage />);
    await selectRows([0, 1]);
    fireEvent.click(screen.getByRole("button", { name: "Move to folder" }));
    fireEvent.click(screen.getByRole("button", { name: /Gone/ }));

    expect(
      await screen.findByText("Session or folder not found"),
    ).toBeInTheDocument();
    expect(screen.getByText("2 selected")).toBeInTheDocument();
  });

  it("disables the Move to folder trigger while folders are still loading", async () => {
    vi.mocked(listMySessions).mockResolvedValue([
      session({ session_id: "sess-1", id: "row-1" }),
    ]);
    vi.mocked(listSessionFolders).mockImplementation(
      () => new Promise<SessionFolder[]>(() => {}),
    );

    render(<SessionsPage />);
    await selectRows([0]);
    expect(screen.getByText("1 selected")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Move to folder" }),
    ).toBeDisabled();
  });
});
