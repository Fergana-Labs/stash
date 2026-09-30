import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import RewardModelsLayout from "./layout";

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
