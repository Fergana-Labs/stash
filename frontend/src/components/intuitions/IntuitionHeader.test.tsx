import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import IntuitionHeader from "./IntuitionHeader";
const { state } = vi.hoisted(() => ({ state: { outputType: "choice", active: true } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("./im-ui", async (importOriginal) => ({
  ...await importOriginal<typeof import("./im-ui")>(),
  useIntuition: () => ({ id: "model", apply: vi.fn(), detail: {
    model: { name: "Support reply", output_type: state.outputType },
    active: state.active ? { number: 2 } : null, draft: { number: 3 },
    judge: { configured: true, provider: "jev", model: "jev-1.13.0" },
  } }),
}));
it.each(["choice", "preference"])("keeps the %s model header focused on its name and actions", (outputType) => {
  state.outputType = outputType;
  render(<IntuitionHeader />);
  expect(screen.getByRole("heading", { name: "Support reply" })).toBeVisible();
  expect(screen.getByRole("button", { name: "More actions" })).toBeVisible();
  for (const metadata of [/Classifier/, /Preference model/, /Active v2/, /Draft v3/, /Evaluator connected/]) {
    expect(screen.queryByText(metadata)).not.toBeInTheDocument();
  }
});
