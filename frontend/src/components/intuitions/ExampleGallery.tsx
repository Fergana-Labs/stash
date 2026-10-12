"use client";

import { useEffect, useState } from "react";
import { errorMessage } from "@/components/reward-models/rm-text";
import { imCatalog, type CatalogExample } from "@/lib/intuition-api";
import { FlagTag } from "./im-ui";
import LoadExampleButton from "./LoadExampleButton";

/** Bundled, pre-graded example models: one card each, loading one creates your own copy. */
export default function ExampleGallery({ heading = true }: { heading?: boolean }) {
  const [examples, setExamples] = useState<CatalogExample[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    imCatalog()
      .then((res) => setExamples(res.examples))
      .catch((e) => setError(errorMessage(e)));
  }, []);

  if (error) return <p className="m-0 text-[12px] text-muted-foreground">Couldn’t load the example gallery: {error}</p>;
  if (examples && examples.length === 0) return null;

  return (
    <section aria-labelledby={heading ? "im-examples-heading" : undefined}>
      {heading && (
        <div className="mb-2.5 flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
          <h2 id="im-examples-heading" className="m-0 text-[14px] font-semibold text-foreground">
            Examples
          </h2>
          <span className="text-[12px] text-muted-foreground">Pre-graded models you can load, run and take apart. Loading makes your own copy.</span>
        </div>
      )}
      <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2">
        {examples === null
          ? [0, 1].map((i) => <div key={i} className="h-40 animate-pulse rounded-lg border border-border bg-surface/50" />)
          : examples.map((ex) => (
              <article key={ex.slug} className="flex min-w-0 flex-col rounded-lg border border-border bg-background px-4 py-3">
                <div className="flex flex-wrap items-start gap-2">
                  <h3 className="m-0 min-w-0 flex-1 basis-40 text-[14px] font-medium text-foreground">{ex.name}</h3>
                  <span className="tag tag-muted shrink-0">{ex.output_type}</span>
                </div>
                {ex.when_to_use && <p className="m-0 mt-1 line-clamp-3 text-[12px] leading-snug text-muted-foreground">{ex.when_to_use}</p>}
                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11.5px] text-muted-foreground">
                  {ex.labels.map((l) => (
                    l.flag ? (
                      <FlagTag key={l.id} label={l.id} />
                    ) : (
                      <span key={l.id} className="tag tag-muted normal-case">
                        {l.id}
                      </span>
                    )
                  ))}
                  <span className="ml-1">
                    <span className="font-mono text-foreground">{ex.examples}</span> examples, pre-graded
                  </span>
                </div>
                <div className="mt-auto flex flex-wrap items-end justify-end gap-3 pt-3">
                  <p className="m-0 min-w-0 flex-1 basis-48 text-[10.5px] leading-snug text-muted-foreground/90">{ex.attribution}</p>
                  <LoadExampleButton slug={ex.slug} name={ex.name} size="sm">
                    Load
                  </LoadExampleButton>
                </div>
              </article>
            ))}
      </div>
    </section>
  );
}
