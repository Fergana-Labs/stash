import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import McpConnectorList from "./McpConnectorList";
import { connectMcpPreset, disconnectMcpServer, listMcpPresets, type McpPreset } from "../../lib/mcp";

vi.mock("../../lib/mcp", () => ({
  listMcpPresets: vi.fn(),
  connectMcpPreset: vi.fn(),
  disconnectMcpServer: vi.fn(),
}));

const renderPreset = (connected: boolean): McpPreset => ({
  name: "render",
  label: "Render",
  url: "https://mcp.render.com/mcp",
  key_help: "Create an API key in Render account settings.",
  tool_allowlist: ["list_services", "list_deploys", "list_logs"],
  connected,
});

describe("McpConnectorList", () => {
  beforeEach(() => {
    vi.mocked(listMcpPresets).mockResolvedValue({ presets: [renderPreset(false)] });
    vi.mocked(connectMcpPreset).mockResolvedValue(undefined);
    vi.mocked(disconnectMcpServer).mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("connects Render by pasting an API key", async () => {
    render(<McpConnectorList workspaceId="ws-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "Connect" }));
    const input = await screen.findByLabelText(/Render API key/);
    fireEvent.change(input, { target: { value: "rnd_secret" } });

    vi.mocked(listMcpPresets).mockResolvedValue({ presets: [renderPreset(true)] });
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));

    await waitFor(() =>
      expect(connectMcpPreset).toHaveBeenCalledWith("ws-1", "render", "rnd_secret")
    );
    expect(await screen.findByText(/agents get 3 read-only tools/)).toBeTruthy();
  });

  it("disconnects a connected provider", async () => {
    vi.mocked(listMcpPresets).mockResolvedValue({ presets: [renderPreset(true)] });
    render(<McpConnectorList workspaceId="ws-1" />);

    fireEvent.click(await screen.findByRole("button", { name: "Disconnect" }));
    await waitFor(() => expect(disconnectMcpServer).toHaveBeenCalledWith("ws-1", "render"));
  });
});
