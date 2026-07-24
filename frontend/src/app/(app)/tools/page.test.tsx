import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ToolsPage from "./page";
import { createMcpServer, deleteMcpServer, listMcpServers, type McpServer } from "@/lib/api";

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

describe("ToolsPage", () => {
  it("lists registered MCP servers with their targets", async () => {
    render(<ToolsPage />);

    expect(await screen.findByText("linear")).toBeTruthy();
    expect(screen.getByText("notion")).toBeTruthy();
    expect(screen.getByText(/npx -y linear-mcp/)).toBeTruthy();
    // Header values are secrets — only key names appear.
    expect(screen.getByText(/headers: Authorization/)).toBeTruthy();
    expect(screen.queryByText(/Bearer tok/)).toBeNull();
  });

  it("adds an http server with parsed headers and refreshes", async () => {
    vi.mocked(createMcpServer).mockResolvedValue(SERVERS[1]);
    render(<ToolsPage />);
    await screen.findByText("linear");

    fireEvent.change(screen.getByLabelText("Server name"), { target: { value: "notion2" } });
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
    render(<ToolsPage />);
    await screen.findByText("linear");

    fireEvent.change(screen.getByLabelText("Server name"), { target: { value: "fs" } });
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

  it("removes a server", async () => {
    vi.mocked(deleteMcpServer).mockResolvedValue(undefined);
    render(<ToolsPage />);
    await screen.findByText("linear");

    fireEvent.click(screen.getAllByRole("button", { name: /remove/i })[0]);

    await waitFor(() => expect(deleteMcpServer).toHaveBeenCalledWith("s1"));
    await waitFor(() => expect(listMcpServers).toHaveBeenCalledTimes(2));
  });
});
