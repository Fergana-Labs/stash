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

  // The empty state is chat-only: setup/onboarding for local agents lives in
  // Settings, not in the conversation (it made the chat read as a docs page).
  it("shows a plain ask-your-agent empty state with no setup guidance", () => {
    render(<ChatPanel sessionId={null} onSessionId={vi.fn()} />);

    expect(screen.getByText("Ask your agent")).toBeInTheDocument();
    expect(screen.queryByText("Connect your local agent")).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText("Ask your agent anything...")).toBeInTheDocument();
  });

  it("replaces the empty state once the first message starts a chat", async () => {
    const onSessionId = vi.fn();
    render(<ChatPanel sessionId={null} onSessionId={onSessionId} />);

    fireEvent.change(screen.getByPlaceholderText("Ask your agent anything..."), {
      target: { value: "What changed recently?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(streamAgentChat).toHaveBeenCalledWith(
        expect.objectContaining({
          message: "What changed recently?",
        }),
      );
    });
    expect(await screen.findByText("Here is what I found.")).toBeInTheDocument();
    expect(screen.queryByText("Ask your agent")).not.toBeInTheDocument();
    expect(onSessionId).toHaveBeenCalledWith("agent-session-1");
  });

  it("sends a launched run by itself, exactly once", async () => {
    // A skill run has no user to press Send: the launcher already collected
    // the request. Re-sending on a re-render would run the skill twice and
    // bill the user for both.
    const run = "Use the resurface skill.\n\nWhat should I revisit?";
    const { rerender } = render(
      <ChatPanel
        sessionId={null}
        onSessionId={vi.fn()}
        openingMessage={run}
      />,
    );

    await waitFor(() => expect(streamAgentChat).toHaveBeenCalledTimes(1));
    expect(streamAgentChat).toHaveBeenCalledWith(
      expect.objectContaining({ message: run }),
    );

    rerender(
      <ChatPanel
        sessionId={null}
        onSessionId={vi.fn()}
        openingMessage={run}
      />,
    );

    expect(streamAgentChat).toHaveBeenCalledTimes(1);
  });

  it("waits for the user when no run was launched into it", async () => {
    render(<ChatPanel sessionId={null} onSessionId={vi.fn()} />);

    await waitFor(() => expect(getAgentChat).not.toHaveBeenCalled());
    expect(streamAgentChat).not.toHaveBeenCalled();
  });
});
