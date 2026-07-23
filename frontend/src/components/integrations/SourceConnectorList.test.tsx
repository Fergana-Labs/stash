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
  window.history.replaceState(null, "", "/");
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

// A failed OAuth callback is a top-window navigation, so the backend can't
// return a JSON error — it redirects to /settings?integration_error=<provider>.
// That failure must be shown loudly (a silent bounce reads as a dead button)
// and the param stripped so a refresh doesn't resurrect a stale error.
describe("SourceConnectorList OAuth callback errors", () => {
  // jsdom has no scrollIntoView; the banner scrolls itself into view because
  // it renders in the fourth settings section, below the fold.
  const scrollIntoView = vi.fn();
  beforeEach(() => {
    Element.prototype.scrollIntoView = scrollIntoView;
  });

  it("shows a banner for ?integration_error and strips it from the URL", async () => {
    window.history.replaceState(
      null,
      "",
      "/settings?integration_error=github&reason=connection_failed"
    );
    listIntegrations.mockResolvedValue({ providers: [connectedGithub(false)] });

    render(
      <ConfirmDialogProvider>
        <SourceConnectorList returnTo="/" includeObsidian={false} />
      </ConfirmDialogProvider>
    );

    expect(await screen.findByText(/GitHub connection failed/)).toBeInTheDocument();
    expect(window.location.pathname).toBe("/settings");
    expect(window.location.search).toBe("");
    expect(scrollIntoView).toHaveBeenCalled();
  });

  it("says the authorization was cancelled for reason=access_denied", async () => {
    window.history.replaceState(
      null,
      "",
      "/settings?integration_error=github&reason=access_denied"
    );
    listIntegrations.mockResolvedValue({ providers: [connectedGithub(false)] });

    render(
      <ConfirmDialogProvider>
        <SourceConnectorList returnTo="/" includeObsidian={false} />
      </ConfirmDialogProvider>
    );

    expect(
      await screen.findByText(/GitHub connection failed — the authorization was cancelled/)
    ).toBeInTheDocument();
  });

  it("never echoes an unrecognized provider slug into the banner", async () => {
    window.history.replaceState(
      null,
      "",
      "/settings?integration_error=Billing%20overdue%20renew%20now&reason=connection_failed"
    );
    listIntegrations.mockResolvedValue({ providers: [connectedGithub(false)] });

    render(
      <ConfirmDialogProvider>
        <SourceConnectorList returnTo="/" includeObsidian={false} />
      </ConfirmDialogProvider>
    );

    expect(await screen.findByText(/^Connection failed/)).toBeInTheDocument();
    expect(screen.queryByText(/Billing overdue/)).not.toBeInTheDocument();
  });

  it("keeps unrelated query params when stripping the error", async () => {
    window.history.replaceState(
      null,
      "",
      "/settings?tab=sources&integration_error=github&reason=connection_failed"
    );
    listIntegrations.mockResolvedValue({ providers: [connectedGithub(false)] });

    render(
      <ConfirmDialogProvider>
        <SourceConnectorList returnTo="/" includeObsidian={false} />
      </ConfirmDialogProvider>
    );

    expect(await screen.findByText(/GitHub connection failed/)).toBeInTheDocument();
    expect(window.location.search).toBe("?tab=sources");
  });

  it("shows no banner without the param", async () => {
    listIntegrations.mockResolvedValue({ providers: [connectedGithub(false)] });

    render(
      <ConfirmDialogProvider>
        <SourceConnectorList returnTo="/" includeObsidian={false} />
      </ConfirmDialogProvider>
    );

    expect(await screen.findByText("GitHub")).toBeInTheDocument();
    expect(screen.queryByText(/connection failed/)).not.toBeInTheDocument();
  });
});

// Visibility is server-driven: only providers the backend returns render a
// card, so customer-specific integrations (Heavi) stay invisible to everyone
// else without the frontend knowing the rules.
describe("SourceConnectorList providers", () => {
  it("offers PostHog as a product analytics source", async () => {
    listIntegrations.mockResolvedValue({
      providers: [{ ...connectedGithub(false), provider: "posthog", display_name: "PostHog" }],
    });

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

  it("hides providers the server does not offer this user", async () => {
    listIntegrations.mockResolvedValue({ providers: [connectedGithub(false)] });

    render(
      <ConfirmDialogProvider>
        <SourceConnectorList returnTo="/" includeObsidian={false} />
      </ConfirmDialogProvider>
    );

    expect(await screen.findByText("GitHub")).toBeInTheDocument();
    expect(screen.queryByText("Heavi")).not.toBeInTheDocument();
    expect(screen.queryByText("PostHog")).not.toBeInTheDocument();
  });
});
