import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import WebsiteDemo from "./WebsiteDemo";
import { demoFixture } from "./website-demo-fixture";

const api = vi.hoisted(() => ({ trace: vi.fn() }));
vi.mock("@/lib/api", () => ({ rmGetTrace: api.trace }));
vi.mock("@/components/BreadcrumbContext", () => ({ useBreadcrumbs: vi.fn() }));
beforeEach(() => {
  api.trace.mockResolvedValue({
    metadata: { website_demo: demoFixture },
    steps: [],
  });
});

it("shows the measured best rather than presenting the latest, worse candidate as the after image", async () => {
  render(<WebsiteDemo traceId="trace-1" />);
  await screen.findByRole("heading", {
    name: "From taste to a better website",
  });
  expect(
    screen.getByAltText("After: rendered Gather landing page, revision 1"),
  ).toBeInTheDocument();
  expect(screen.getAllByText(/91.0%/).length).toBeGreaterThan(0);
  expect(screen.getByText(/Recorded agent run/)).toBeInTheDocument();
});

it("keeps rejected revisions inspectable and treats their HTML as text", async () => {
  const { container } = render(<WebsiteDemo traceId="trace-1" />);
  await screen.findByRole("heading", {
    name: "From taste to a better website",
  });
  fireEvent.click(screen.getByRole("button", { name: /Agent run$/ }));
  fireEvent.click(
    screen.getByRole("button", { name: /Candidate 2.*Rejected/ }),
  );
  expect(
    screen.getByAltText(
      "Candidate 2: rendered Gather landing page, revision 2",
    ),
  ).toBeInTheDocument();
  expect(container.querySelector("pre")?.textContent).toContain(
    "<script>window.executed = true</script>",
  );
  expect(container.querySelector("iframe, script")).toBeNull();
  expect(api.trace).toHaveBeenCalledWith("trace-1", true);
});

it("reports an inaccessible trace instead of showing another account's demo", async () => {
  api.trace.mockRejectedValueOnce(new Error("Trace not found"));
  render(<WebsiteDemo traceId="other-owner" />);
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Trace not found"),
  );
});
