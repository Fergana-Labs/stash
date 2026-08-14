import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import IntegrationsPage from "./page";
import { createMcpServer, deleteMcpServer, listMcpServers, type McpServer } from "@/lib/api";
import { listIntegrations } from "@/lib/integrations";

const router = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

// A stable user object — a fresh literal per render would retrigger the
// [user]-dependent load effect and break call-count assertions.
const authState = vi.hoisted(() => ({ user: { id: "u1", name: "sam" }, loading: false }));

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => authState,
}));

vi.mock("@/components/BreadcrumbContext", () => ({
  useBreadcrumbs: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: { error: vi.fn() },
}));

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
    }
  },
  listMcpServers: vi.fn(),
  createMcpServer: vi.fn(),
  deleteMcpServer: vi.fn(),
  // The integrations grid above the MCP registry loads these on mount.
  listSources: vi.fn().mockResolvedValue([]),
  // The coding-agents section shows which agents are already sending sessions.
  listAgentNames: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/lib/integrations", () => ({
  INTEGRATIONS_CHANGED_EVENT: "integrations-changed",
  listIntegrations: vi.fn().mockResolvedValue({ providers: [] }),
}));

const SERVERS: McpServer[] = [
  {
    id: "s1",
    name: "linear",
    transport: "stdio",
    command: "npx -y linear-mcp",
    url: null,
    headers: {},
    env: {},
    created_at: "2026-07-22T00:00:00Z",
  },
  {
    id: "s2",
    name: "notion",
    transport: "http",
    command: null,
    url: "https://mcp.notion.com/mcp",
    headers: { Authorization: "Bearer tok" },
    env: {},
    created_at: "2026-07-22T00:00:00Z",
  },
];

beforeEach(() => {
  vi.mocked(listMcpServers).mockResolvedValue(SERVERS);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("IntegrationsPage", () => {
  it("lists registered MCP servers", async () => {
    render(<IntegrationsPage />);

    expect(await screen.findByText("linear")).toBeTruthy();
    expect(screen.getByText("notion")).toBeTruthy();
    // The card describes the server in words; the raw target belongs to the
    // manage dialog, not the grid.
    expect(screen.getByText(/a local npx process/)).toBeTruthy();
    expect(screen.getByText(/mcp\.notion\.com/)).toBeTruthy();
  });

  it("shows a server's target and header names in manage, never header values", async () => {
    render(<IntegrationsPage />);
    await screen.findByText("notion");

    // The http server is the one carrying headers.
    fireEvent.click(screen.getAllByRole("button", { name: /^manage$/i })[1]);

    expect(await screen.findByText("https://mcp.notion.com/mcp")).toBeTruthy();
    // Header values are secrets — only key names appear.
    expect(screen.getByText("Authorization")).toBeTruthy();
    expect(screen.queryByText(/Bearer tok/)).toBeNull();
  });

  it("adds an http server with parsed headers and refreshes", async () => {
    vi.mocked(createMcpServer).mockResolvedValue(SERVERS[1]);
    render(<IntegrationsPage />);
    await screen.findByText("linear");

    fireEvent.click(screen.getByRole("button", { name: /^add$/i }));
    fireEvent.change(await screen.findByLabelText("Server name"), { target: { value: "notion2" } });
    fireEvent.change(screen.getByLabelText("URL"), {
      target: { value: "https://mcp.example.com/mcp" },
    });
    fireEvent.change(screen.getByLabelText("Headers"), {
      target: { value: "Authorization=Bearer abc" },
    });
    fireEvent.click(screen.getByRole("button", { name: /add server/i }));

    await waitFor(() =>
      expect(createMcpServer).toHaveBeenCalledWith({
        name: "notion2",
        transport: "http",
        url: "https://mcp.example.com/mcp",
        headers: { Authorization: "Bearer abc" },
      })
    );
    // The list is re-fetched after a successful add.
    await waitFor(() => expect(listMcpServers).toHaveBeenCalledTimes(2));
  });

  it("adds a stdio server with a command", async () => {
    vi.mocked(createMcpServer).mockResolvedValue(SERVERS[0]);
    render(<IntegrationsPage />);
    await screen.findByText("linear");

    fireEvent.click(screen.getByRole("button", { name: /^add$/i }));
    fireEvent.change(await screen.findByLabelText("Server name"), { target: { value: "fs" } });
    fireEvent.click(screen.getByRole("radio", { name: /local \(stdio\)/i }));
    fireEvent.change(screen.getByLabelText("Command"), {
      target: { value: "npx -y fs-mcp" },
    });
    fireEvent.click(screen.getByRole("button", { name: /add server/i }));

    await waitFor(() =>
      expect(createMcpServer).toHaveBeenCalledWith({
        name: "fs",
        transport: "stdio",
        command: "npx -y fs-mcp",
      })
    );
  });

  // A failed integrations load used to leave the grid on skeletons forever,
  // so the user could never tell that "not connected" was really "unknown".
  it("surfaces a failed integrations load instead of skeletons", async () => {
    vi.mocked(listIntegrations).mockRejectedValueOnce(new Error("integrations are down"));
    render(<IntegrationsPage />);

    expect(await screen.findByText(/integrations are down/)).toBeTruthy();
  });

  // Removing is deliberately behind Manage: the grid's action must never
  // delete a server in one click, since it sits where every other box has a
  // harmless navigation.
  it("removes a server from its manage dialog", async () => {
    vi.mocked(deleteMcpServer).mockResolvedValue(undefined);
    render(<IntegrationsPage />);
    await screen.findByText("linear");

    expect(screen.queryByRole("button", { name: /^remove/i })).toBeNull();

    fireEvent.click(screen.getAllByRole("button", { name: /^manage$/i })[0]);
    fireEvent.click(await screen.findByRole("button", { name: /remove server/i }));

    await waitFor(() => expect(deleteMcpServer).toHaveBeenCalledWith("s1"));
    await waitFor(() => expect(listMcpServers).toHaveBeenCalledTimes(2));
  });
});
