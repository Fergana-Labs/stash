import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ChatPanel from "./ChatPanel";
import { getAgentChat, streamAgentChat } from "@/lib/agentChat";

vi.mock("@/lib/agentChat", () => ({
  getAgentChat: vi.fn(),
  agentTurnRunning: vi.fn().mockResolvedValue(false),
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
    vi.unstubAllGlobals();
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

  it("keeps an earlier turn visible while the next response streams", async () => {
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
    vi.stubGlobal("CSS", { escape: (id: string) => id.replace(/[^a-zA-Z0-9_-]/g, "\\$&") });
    vi.mocked(getAgentChat).mockResolvedValue([
      { role: "user", content: "First question" },
      { role: "assistant", content: "First answer" },
      { role: "user", content: "Second question" },
      { role: "assistant", content: "Second answer" },
    ]);
    let handlers: Parameters<typeof streamAgentChat>[0];
    let finish!: () => void;
    vi.mocked(streamAgentChat).mockImplementation((options) => {
      handlers = options;
      return new Promise<void>((resolve) => { finish = resolve; });
    });
    render(<ChatPanel sessionId="existing-chat" onSessionId={vi.fn()} />);
    await screen.findByText("First answer");
    fireEvent.change(screen.getByPlaceholderText("Ask your agent anything..."), { target: { value: "Third question" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(streamAgentChat).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Message 1: First question" }));
    vi.mocked(Element.prototype.scrollTo).mockClear();
    await act(async () => { handlers.onText?.("Streaming the third answer"); });
    expect(Element.prototype.scrollTo).not.toHaveBeenCalled();
    await act(async () => { finish(); });
    expect(Element.prototype.scrollTo).not.toHaveBeenCalled();
  });
});
