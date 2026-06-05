import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ChatPanel from "./ChatPanel";
import { getAgentChat, streamAgentChat } from "@/lib/agentChat";

vi.mock("@/lib/agentChat", () => ({
  getAgentChat: vi.fn(),
  streamAgentChat: vi.fn(),
}));

describe("ChatPanel", () => {
  beforeEach(() => {
    Element.prototype.scrollTo = vi.fn();
    vi.mocked(getAgentChat).mockResolvedValue([]);
    vi.mocked(streamAgentChat).mockImplementation(async (opts) => {
      opts.onSession?.("agent-session-1");
      opts.onText?.("Here is what I found.");
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows setup guidance inside the empty chat state", () => {
    render(<ChatPanel workspaceId="ws-1" sessionId={null} onSessionId={vi.fn()} />);

    expect(screen.getByText("Chat with your agent")).toBeInTheDocument();
    expect(screen.getByText("Connect your local agent")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Ask your agent anything...")).toBeInTheDocument();
  });

  it("hides setup guidance after the first message starts a chat", async () => {
    const onSessionId = vi.fn();
    render(<ChatPanel workspaceId="ws-1" sessionId={null} onSessionId={onSessionId} />);

    fireEvent.change(screen.getByPlaceholderText("Ask your agent anything..."), {
      target: { value: "What changed recently?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(streamAgentChat).toHaveBeenCalledWith(
        expect.objectContaining({
          message: "What changed recently?",
          workspaceId: "ws-1",
        }),
      );
    });
    expect(await screen.findByText("Here is what I found.")).toBeInTheDocument();
    expect(screen.queryByText("Connect your local agent")).not.toBeInTheDocument();
    expect(onSessionId).toHaveBeenCalledWith("agent-session-1");
  });
});
