import AppRedirectForSignedInUsers from "./AppRedirectForSignedInUsers";

import ResearchLandscape from "./ResearchLandscape";

const APP_URL = process.env.MANAGED_APP_URL || "https://app.joinstash.ai";

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col bg-background text-foreground">
      <AppRedirectForSignedInUsers appUrl={APP_URL} />
      <div className="mx-auto w-full max-w-[680px] px-6 pb-8 pt-12 sm:pt-20">
        <header className="mb-10 flex items-center gap-3">
          <span aria-hidden="true" className="h-3 w-3 rounded-full bg-brand" />
          <h1 className="font-display text-[40px] font-medium tracking-[-0.04em] text-ink">Stash</h1>
        </header>
        <div className="space-y-5 text-[17px] leading-[1.75]">
          <p className="text-ink">
            Stash is a platform enabling verifiers for non-deterministic domains
            and long horizon agents.
          </p>
          <p>
            RLVR has enabled agents to solve Millennium prize problems but
            progress is plateauing outside of coding &amp; math. Recent advances
            in mechanistic interpretability allow us to build off of a model’s
            “gut feeling,” enabling the verifiers that will power the next era of
            AI scaling.
          </p>
        </div>
        <section aria-labelledby="who-we-are" className="mt-9">
          <h2 id="who-we-are" className="mb-3 font-display text-[20px] font-medium text-ink">Who we are</h2>
          <p className="text-[17px] leading-[1.75]">
            We are a team of builders and researchers based in San Francisco, CA.
          </p>
        </section>
        <section aria-labelledby="contact" className="mt-8">
          <h2 id="contact" className="mb-3 font-display text-[20px] font-medium text-ink">Contact</h2>
          <p className="text-[17px] leading-[1.75]">
            If you think this sounds interesting, we’d love to chat. Please reach us at{" "}
            <a href="mailto:sam@joinstash.ai" className="text-brand-ink underline decoration-brand/40 underline-offset-4 hover:decoration-brand focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-brand">
              sam@joinstash.ai
            </a>.
          </p>
        </section>
      </div>
      <ResearchLandscape />
    </main>
  );
}
