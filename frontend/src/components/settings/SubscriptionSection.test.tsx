import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SubscriptionSection from "./SubscriptionSection";
import { getBilling, setOverageLimit, type BillingInfo } from "../../lib/api";

vi.mock("../../lib/api", () => ({
  getBilling: vi.fn(), setOverageLimit: vi.fn(), startCheckout: vi.fn(),
  openBillingPortal: vi.fn(), redeemCode: vi.fn(),
}));

const pro: BillingInfo = {
  billing_enabled: true, plan: "pro", status: "active", transcript_tokens: 2500000,
  included_tokens: 2000000, remaining_tokens: 0, resets_at: "2026-10-01T00:00:00+00:00",
  overage_cents: 500, overage_limit_cents: 0, overages_enabled: false,
  overage_cents_per_million: 1000, free_included_tokens: 100000, pro_included_tokens: 2000000,
};

beforeEach(() => { vi.resetAllMocks(); vi.mocked(getBilling).mockResolvedValue(pro); });

describe("transcript usage billing", () => {
  it("shows usage and requires explicit saving before authorizing overages", async () => {
    vi.mocked(setOverageLimit).mockResolvedValue({ ...pro, overages_enabled: true, overage_limit_cents: 2000 });
    render(<SubscriptionSection />);
    expect(await screen.findByText(/Overages disabled\./)).toBeTruthy();
    expect(screen.getByText(/2,500,000 tokens curated/)).toBeTruthy();
    expect(screen.getByText(/\$10.00 per million/)).toBeTruthy();
    expect(screen.getByText(/October 1 at 00:00 UTC/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Monthly overage spending limit in dollars"), { target: { value: "20" } });
    expect(setOverageLimit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Save spending limit" }));
    await waitFor(() => expect(setOverageLimit).toHaveBeenCalledWith(2000));
    expect(await screen.findByText(/Overages enabled\./)).toBeTruthy();
  });

  it("keeps overages disabled and surfaces server failures", async () => {
    vi.mocked(setOverageLimit).mockRejectedValue(new Error("Usage billing has not been configured"));
    render(<SubscriptionSection />);
    const input = await screen.findByLabelText("Monthly overage spending limit in dollars");
    fireEvent.change(input, { target: { value: "20" } });
    fireEvent.click(screen.getByRole("button", { name: "Save spending limit" }));
    expect(await screen.findByText("Usage billing has not been configured")).toBeTruthy();
    expect(screen.getByText(/Overages disabled\./)).toBeTruthy();
  });

  it("does not offer paid overages on Free", async () => {
    vi.mocked(getBilling).mockResolvedValue({ ...pro, plan: "free", status: null, transcript_tokens: 100000, included_tokens: 100000 });
    render(<SubscriptionSection />);
    expect(await screen.findByText(/100,000 transcript tokens included/)).toBeTruthy();
    expect(screen.queryByLabelText("Monthly overage spending limit in dollars")).toBeNull();
    expect(screen.getByText(/Curation is paused/)).toBeTruthy();
  });
});
