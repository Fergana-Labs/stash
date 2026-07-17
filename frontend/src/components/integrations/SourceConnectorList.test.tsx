import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { IntegrationStatus } from "../../lib/integrations";
import { ConfirmDialogProvider } from "../ConfirmDialog";
import SourceConnectorList from "./SourceConnectorList";

const listIntegrations = vi.fn();
const disconnectIntegration = vi.fn();
const listSources = vi.fn();

vi.mock("@/lib/integrations", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/integrations")>();
  return {
    ...actual,
    listIntegrations: () => listIntegrations(),
    disconnectIntegration: (...args: unknown[]) => disconnectIntegration(...args),
  };
});

// The connector list also fetches sources to mark extension-fed connectors
// (X / Instagram) connected; default to none so OAuth connectors render.
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    listSources: () => listSources(),
  };
});

function connectedGithub(connected: boolean): IntegrationStatus {
  return {
    provider: "github",
    display_name: "GitHub",
    scopes: [],
    connected,
    enabled: true,
    disabled_reason: null,
    account_email: null,
    account_display_name: connected ? "Henry Dowling" : null,
    expires_at: null,
    connected_at: null,
    accounts: [],
    auth_kind: "oauth",
    credential_fields: null,
  };
}

beforeEach(() => {
  listSources.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// Disconnect lives in the connect modal itself so a connected source can be
// removed without first navigating into its detail page.
describe("SourceConnectorList disconnect", () => {
  it("confirms, then disconnects the provider and refreshes", async () => {
    listIntegrations
      .mockResolvedValueOnce({ providers: [connectedGithub(true)] })
      .mockResolvedValueOnce({ providers: [connectedGithub(false)] });
    disconnectIntegration.mockResolvedValue(undefined);

    render(
      <ConfirmDialogProvider>
        <SourceConnectorList returnTo="/" includeObsidian={false} />
      </ConfirmDialogProvider>
    );

    const disconnect = await screen.findByRole("button", { name: "Disconnect" });
    fireEvent.click(disconnect);

    // Confirm in the dialog rather than firing the destructive action immediately.
    fireEvent.click(await screen.findByText("Disconnect", { selector: "button.bg-red-600" }));

    await waitFor(() => expect(disconnectIntegration).toHaveBeenCalledWith("github"));
    expect(listIntegrations).toHaveBeenCalledTimes(2);
  });

  it("does nothing when the confirmation is cancelled", async () => {
    listIntegrations.mockResolvedValue({ providers: [connectedGithub(true)] });

    render(
      <ConfirmDialogProvider>
        <SourceConnectorList returnTo="/" includeObsidian={false} />
      </ConfirmDialogProvider>
    );

    fireEvent.click(await screen.findByRole("button", { name: "Disconnect" }));
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));

    expect(disconnectIntegration).not.toHaveBeenCalled();
  });
});

describe("SourceConnectorList providers", () => {
  it("offers PostHog as a product analytics source", async () => {
    listIntegrations.mockResolvedValue({ providers: [] });

    render(
      <ConfirmDialogProvider>
        <SourceConnectorList returnTo="/" includeObsidian={false} />
      </ConfirmDialogProvider>
    );

    expect(await screen.findByText("PostHog")).toBeInTheDocument();
    expect(
      screen.getByText("Browse dashboards, insights, feature flags, and experiments.")
    ).toBeInTheDocument();
  });
});
