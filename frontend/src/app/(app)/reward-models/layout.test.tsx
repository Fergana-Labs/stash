import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import RewardModelsLayout from "./layout";
import { ProductCheckpointProvider } from "@/components/ProductCheckpointContext";

const route = vi.hoisted(() => ({ pathname: "/reward-models", replace: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => route.pathname, useRouter: () => ({ replace: route.replace }) }));
beforeEach(() => { route.pathname = "/reward-models"; route.replace.mockClear(); });

const auth = vi.hoisted(() => ({ loading: false, user: { reward_models_enabled: false } }));
vi.mock("@/hooks/useAuth", () => ({ useAuth: () => auth }));

it.each([true, false])("protects direct reward links according to the account flag (%s)", (enabled) => {
  auth.user.reward_models_enabled = enabled;
  render(<RewardModelsLayout><button>Import traces</button></RewardModelsLayout>);
  expect(screen.queryByRole("button", { name: "Import traces" }) !== null).toBe(enabled);
});

it("does not mount reward pages before the account flag loads", () => {
  auth.loading = true;
  render(<RewardModelsLayout><button>Import traces</button></RewardModelsLayout>);
  expect(screen.queryByRole("button", { name: "Import traces" })).not.toBeInTheDocument();
  auth.loading = false;
});

it.each(["review", "changes", "graders"])("redirects newer %s routes away from the checkpoint", (page) => {
  auth.user.reward_models_enabled = true;
  route.pathname = `/reward-models/${page}`;
  render(<ProductCheckpointProvider checkpoint="floodgate-2026-10-05"><RewardModelsLayout><button>New workbench</button></RewardModelsLayout></ProductCheckpointProvider>);
  expect(screen.queryByRole("button", { name: "New workbench" })).not.toBeInTheDocument();
  expect(route.replace).toHaveBeenCalledWith("/reward-models");
});
