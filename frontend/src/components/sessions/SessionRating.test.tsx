import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { rateSession } from "@/lib/api";
import SessionRating from "./SessionRating";

vi.mock("@/lib/api", () => ({
  rateSession: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SessionRating", () => {
  it("saves a verdict and reports it back", async () => {
    vi.mocked(rateSession).mockResolvedValue({ rating: "good" });
    const onChange = vi.fn();
    render(<SessionRating sessionId="sess-1" rating={null} onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: "Good session" }));

    await waitFor(() => expect(onChange).toHaveBeenCalledWith("good"));
    expect(rateSession).toHaveBeenCalledWith("sess-1", "good");
  });

  it("clears the verdict when the active one is clicked again", async () => {
    vi.mocked(rateSession).mockResolvedValue({ rating: null });
    const onChange = vi.fn();
    render(<SessionRating sessionId="sess-1" rating="bad" onChange={onChange} />);

    expect(screen.getByRole("button", { name: "Bad session" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "Bad session" }));

    await waitFor(() => expect(rateSession).toHaveBeenCalledWith("sess-1", null));
  });
});
