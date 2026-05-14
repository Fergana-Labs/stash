"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";

export type HtmlLayout = "responsive" | "fixed-aspect";

type Props = {
  html: string;
  title: string;
  layout?: HtmlLayout;
};

// Iframes don't auto-size to their content — the parent has to decide the
// box. Two modes:
//
// - "fixed-aspect": locks a 16:9 canvas. Right for slides/decks where the
//   page has an intentional design size.
// - "responsive": injects a tiny bootstrap into the sandboxed document that
//   reports its scrollHeight back on every ResizeObserver tick AND on demand
//   when the parent pings. The parent pings on iframe load to avoid losing
//   the first measurement to hydration-timing races, then keeps listening
//   for spontaneous resize messages.
//
// Both modes share `sandbox="allow-scripts"` — postMessage works across the
// opaque-origin boundary, so we don't widen the sandbox for resize.
export default function HtmlPageView({ html, title, layout = "responsive" }: Props) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [height, setHeight] = useState<number | null>(null);
  const channel = `stash-resize-${useId()}`;

  const srcDoc = useMemo(
    () => (layout === "responsive" ? injectResizeBootstrap(html, channel) : html),
    [html, layout, channel],
  );

  useEffect(() => {
    if (layout !== "responsive") return;
    function onMessage(e: MessageEvent) {
      const data = e.data;
      if (
        data &&
        typeof data === "object" &&
        data.type === "stash:resize" &&
        data.channel === channel &&
        typeof data.height === "number"
      ) {
        setHeight(Math.max(0, Math.ceil(data.height)));
      }
    }
    window.addEventListener("message", onMessage);
    // The iframe's bootstrap posts its height once at load time, but if the
    // iframe finished loading before this effect attached, that initial post
    // was lost. Probe the iframe so it re-posts now that we're listening.
    iframeRef.current?.contentWindow?.postMessage(
      { type: "stash:probe", channel },
      "*",
    );
    return () => window.removeEventListener("message", onMessage);
  }, [layout, channel]);

  // Future iframe loads (srcDoc swap, navigation) re-trigger a probe.
  function onIframeLoad() {
    if (layout !== "responsive") return;
    iframeRef.current?.contentWindow?.postMessage(
      { type: "stash:probe", channel },
      "*",
    );
  }

  if (layout === "fixed-aspect") {
    return (
      <iframe
        ref={iframeRef}
        srcDoc={html}
        sandbox="allow-scripts"
        title={title}
        style={{ width: "100%", aspectRatio: "16 / 9", border: 0, display: "block" }}
      />
    );
  }

  return (
    <iframe
      ref={iframeRef}
      srcDoc={srcDoc}
      sandbox="allow-scripts"
      title={title}
      onLoad={onIframeLoad}
      style={{
        width: "100%",
        height: height ?? 200,
        border: 0,
        display: "block",
      }}
    />
  );
}

// Appended just before </body>. Lives inside the sandbox like any other
// script in the document — adding it doesn't widen the trust boundary.
function injectResizeBootstrap(html: string, channel: string): string {
  const script = `<script>(function(){
    var c=${JSON.stringify(channel)};
    function post(){
      var h=Math.max(
        document.documentElement.scrollHeight,
        document.body ? document.body.scrollHeight : 0
      );
      parent.postMessage({type:"stash:resize",channel:c,height:h},"*");
    }
    new ResizeObserver(post).observe(document.documentElement);
    if(document.body) new ResizeObserver(post).observe(document.body);
    window.addEventListener("message",function(e){
      if(e.data && e.data.type==="stash:probe" && e.data.channel===c) post();
    });
    post();
  })();</script>`;
  if (/<\/body>/i.test(html)) return html.replace(/<\/body>/i, `${script}</body>`);
  return html + script;
}
