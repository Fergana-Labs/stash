"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";

// "full-width" renders exactly like "responsive" here (auto-height iframe at
// width:100%); the difference is purely the parent's column width, set in
// PageClient. So every check below treats anything that isn't "fixed-aspect"
// as the responsive path.
export type HtmlLayout = "responsive" | "fixed-aspect" | "full-width" | "app";

export type HtmlSelectionInfo = {
  quoted_text: string;
  prefix: string;
  suffix: string;
  /** Bounding rect of the selection's **last line**, in iframe viewport
   *  coords. The parent uses this to anchor a floating toolbar above the
   *  caret instead of guessing at offsets. */
  rect: { top: number; left: number; right: number; bottom: number };
};

type Props = {
  html: string;
  title: string;
  layout?: HtmlLayout;
  /** Surfaces a selection event from inside the iframe to the parent
   *  so the parent can show a "Comment" button anchored to it. The
   *  `endX/endY` are relative to the iframe's viewport. */
  onSelection?: (info: HtmlSelectionInfo | null) => void;
  /** Click on a `[data-comment-id]` span inside the iframe asks the
   *  parent to surface the matching thread. */
  onActivateThread?: (threadId: string | null) => void;
  onAnchorTops?: (anchorTops: Record<string, number>) => void;
  /** Wraps the most recently reported selection with a
   *  `<span data-comment-id>` and posts the resulting full HTML back
   *  via `onHtmlMutated`. Called by the parent after the thread is
   *  created on the server. */
  pendingWrapId?: string | null;
  onWrapComplete?: () => void;
  onHtmlMutated?: (nextHtml: string) => void;
  onNavigateLink?: (href: string) => void;
  /** Highlight the currently selected thread's anchor span. */
  activeThreadId?: string | null;
  /** Strip the wrapper for the named thread (after the user deletes it).
   *  Pass a fresh `nonce` each time so the iframe re-runs the unwrap. */
  stripCommentToken?: { id: string; nonce: number } | null;
  /** Light WYSIWYG: when true, the iframe's body becomes `contenteditable`
   *  and posts debounced `stash:html-mutated` events as the user types.
   *  The iframe is the source of truth while editable — we don't reflow
   *  it from `html` prop changes, so the user's caret position survives
   *  the save round-trip. */
  editable?: boolean;
  /** When set, this HTML page is a hosted dashboard: inject `window.stash`
   *  (a read-only data-API client bound to a short-lived token) into the
   *  sandboxed iframe so the page can read its workspace's data. */
  dashboard?: { token: string; workspaceId: string; apiBase: string } | null;
};

// Iframes don't auto-size to their content — the parent has to decide the
// box. Two modes:
//
// - "fixed-aspect": locks a 16:9 canvas. Right for slides where the
//   page has an intentional design size.
// - "responsive": injects a tiny bootstrap into the sandboxed document that
//   reports its scrollHeight back on every ResizeObserver tick AND on demand
//   when the parent pings. The parent pings on iframe load to avoid losing
//   the first measurement to hydration-timing races, then keeps listening
//   for spontaneous resize messages.
//
// Both modes share `sandbox="allow-scripts"` — postMessage works across the
// opaque-origin boundary, so we don't widen the sandbox for resize.
export default function HtmlPageView({
  html,
  title,
  layout = "responsive",
  onSelection,
  onActivateThread,
  onAnchorTops,
  pendingWrapId,
  onWrapComplete,
  onHtmlMutated,
  onNavigateLink,
  activeThreadId,
  stripCommentToken,
  editable = false,
  dashboard,
}: Props) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const presentWrapRef = useRef<HTMLDivElement | null>(null);
  const [height, setHeight] = useState<number | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const channel = `stash-resize-${useId()}`;

  // The iframe's DOM is authoritative for its lifetime. We pin srcDoc to the
  // first `html` we see so saves (wrap, edit, unwrap) don't reload the iframe
  // and trash the user's caret. Switching pages remounts this component, so
  // a new page picks up its own initial html cleanly.
  const [initialHtml] = useState(html);

  // Slide-deck detection: any fixed-aspect HTML page whose body contains
  // <section class="slide"> elements gets prev/next navigation. Pages
  // with zero such sections render exactly as before — single frame.
  const slideCount = useMemo(
    () =>
      layout === "fixed-aspect"
        ? (initialHtml.match(/<section\b[^>]*\bclass\s*=\s*["'][^"']*\bslide\b/gi) ?? []).length
        : 0,
    [layout, initialHtml],
  );
  const isDeck = slideCount > 0;
  const [activeSlide, setActiveSlide] = useState(0);

  const srcDoc = useMemo(() => {
    if (layout === "fixed-aspect") {
      return isDeck ? injectSlideDeckBootstrap(initialHtml, channel) : initialHtml;
    }
    let out = injectResizeBootstrap(initialHtml, channel, Boolean(onNavigateLink));
    if (layout === "app") {
      const apiOrigin =
        dashboard?.apiBase ?? (typeof window !== "undefined" ? window.location.origin : "");
      out = injectAppShell(out, apiOrigin, dashboard ?? null);
    }
    return out;
  }, [layout, channel, initialHtml, isDeck, onNavigateLink, dashboard]);

  useEffect(() => {
    function onMessage(e: MessageEvent) {
      const data = e.data;
      if (!data || typeof data !== "object" || data.channel !== channel) return;
      if (data.type === "skill:resize" && typeof data.height === "number") {
        if (layout !== "fixed-aspect") setHeight(Math.max(0, Math.ceil(data.height)));
        return;
      }
      if (data.type === "skill:selection") {
        if (data.cleared) {
          onSelection?.(null);
          return;
        }
        const r = data.rect ?? {};
        onSelection?.({
          quoted_text: String(data.quoted_text ?? ""),
          prefix: String(data.prefix ?? ""),
          suffix: String(data.suffix ?? ""),
          rect: {
            top: Number(r.top ?? 0),
            left: Number(r.left ?? 0),
            right: Number(r.right ?? 0),
            bottom: Number(r.bottom ?? 0),
          },
        });
        return;
      }
      if (data.type === "skill:thread-click" && typeof data.id === "string") {
        onActivateThread?.(data.id);
        return;
      }
      if (data.type === "skill:thread-deselect") {
        onActivateThread?.(null);
        return;
      }
      if (data.type === "skill:anchor-tops" && data.anchorTops) {
        const anchorTops: Record<string, number> = {};
        for (const [id, top] of Object.entries(data.anchorTops)) {
          if (typeof top === "number") anchorTops[id] = top;
        }
        onAnchorTops?.(anchorTops);
        return;
      }
      if (data.type === "stash:html-mutated" && typeof data.html === "string") {
        onHtmlMutated?.(data.html);
        onWrapComplete?.();
        return;
      }
      if (data.type === "skill:navigate" && typeof data.href === "string") {
        onNavigateLink?.(data.href);
        return;
      }
    }
    window.addEventListener("message", onMessage);
    iframeRef.current?.contentWindow?.postMessage(
      { type: "skill:probe", channel },
      "*",
    );
    return () => window.removeEventListener("message", onMessage);
  }, [
    layout,
    channel,
    onSelection,
    onActivateThread,
    onAnchorTops,
    onHtmlMutated,
    onWrapComplete,
    onNavigateLink,
  ]);

  // Send `pendingWrapId` down to the iframe whenever it changes. Iframe
  // wraps its current selection in `<span data-comment-id="id">`, posts
  // back the new full HTML, then we ack via `onWrapComplete`.
  useEffect(() => {
    if (!pendingWrapId) return;
    iframeRef.current?.contentWindow?.postMessage(
      { type: "skill:wrap", channel, id: pendingWrapId },
      "*",
    );
  }, [pendingWrapId, channel]);

  // Push active thread id to the iframe so it can style the matching span.
  useEffect(() => {
    iframeRef.current?.contentWindow?.postMessage(
      { type: "skill:active", channel, id: activeThreadId ?? null },
      "*",
    );
  }, [activeThreadId, channel]);

  // Strip the inline `<span data-comment-id>` wrapper for a just-deleted
  // thread. The iframe unwraps and posts back the new HTML, which the
  // parent saves via `onHtmlMutated`.
  useEffect(() => {
    if (!stripCommentToken) return;
    iframeRef.current?.contentWindow?.postMessage(
      { type: "skill:unwrap", channel, id: stripCommentToken.id },
      "*",
    );
  }, [stripCommentToken, channel]);

  // Push edit-mode to the iframe whenever it changes.
  useEffect(() => {
    iframeRef.current?.contentWindow?.postMessage(
      { type: "skill:set-editable", channel, enabled: editable },
      "*",
    );
  }, [editable, channel]);

  // Push the active slide index to the iframe so the bootstrap shows
  // just that section.
  useEffect(() => {
    if (!isDeck) return;
    iframeRef.current?.contentWindow?.postMessage(
      { type: "stash:slide-goto", channel, index: activeSlide },
      "*",
    );
  }, [isDeck, activeSlide, channel]);

  // Keyboard nav when the deck is on screen. We bail when the user is
  // typing somewhere (any input/textarea/contenteditable), otherwise
  // arrow keys would silently steal focus from the comment composer,
  // share modal, page-title editor, etc. Fullscreen-only keys (Space,
  // PageDown/Up, Home/End) work everywhere too so casual viewing also
  // gets the upgrade.
  useEffect(() => {
    if (!isDeck) return;
    function isTypingTarget(node: Element | null): boolean {
      if (!node) return false;
      const tag = node.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
      // contenteditable can be inherited; closest() walks ancestors.
      if (node.closest?.("[contenteditable='true'], [contenteditable='']"))
        return true;
      return false;
    }
    function onKey(e: KeyboardEvent) {
      if (isTypingTarget(document.activeElement)) return;
      if (e.key === "ArrowRight" || e.key === "PageDown" || e.key === " ") {
        setActiveSlide((s) => Math.min(slideCount - 1, s + 1));
        e.preventDefault();
      } else if (e.key === "ArrowLeft" || e.key === "PageUp") {
        setActiveSlide((s) => Math.max(0, s - 1));
        e.preventDefault();
      } else if (e.key === "Home") {
        setActiveSlide(0);
        e.preventDefault();
      } else if (e.key === "End") {
        setActiveSlide(slideCount - 1);
        e.preventDefault();
      } else if (e.key === "f" || e.key === "F") {
        // F toggles fullscreen. Esc exits (browser default).
        const el = presentWrapRef.current;
        if (!el) return;
        if (document.fullscreenElement === el) {
          document.exitFullscreen?.();
        } else {
          el.requestFullscreen?.();
        }
        e.preventDefault();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isDeck, slideCount]);

  // Track fullscreen state so we can letterbox the iframe and toggle the
  // click-to-advance overlay.
  useEffect(() => {
    function onChange() {
      setIsFullscreen(document.fullscreenElement === presentWrapRef.current);
    }
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  const enterPresent = () => {
    presentWrapRef.current?.requestFullscreen?.();
  };
  const advanceInPresent = () => {
    setActiveSlide((s) => Math.min(slideCount - 1, s + 1));
  };

  function onIframeLoad() {
    iframeRef.current?.contentWindow?.postMessage(
      { type: "skill:probe", channel },
      "*",
    );
  }

  if (layout === "fixed-aspect") {
    return (
      <div style={{ position: "relative", width: "100%" }}>
        <div
          ref={presentWrapRef}
          data-fullscreen={isFullscreen ? "true" : "false"}
          style={{
            position: "relative",
            width: "100%",
            // Letterbox in fullscreen: black backdrop, 16:9 iframe centered.
            background: isFullscreen ? "#000" : "transparent",
            display: isFullscreen ? "flex" : "block",
            alignItems: "center",
            justifyContent: "center",
            height: isFullscreen ? "100vh" : undefined,
          }}
        >
          <iframe
            ref={iframeRef}
            srcDoc={srcDoc}
            sandbox="allow-scripts"
            title={title}
            onLoad={onIframeLoad}
            style={
              isFullscreen
                ? {
                    width: "min(100vw, calc(100vh * 16 / 9))",
                    aspectRatio: "16 / 9",
                    border: 0,
                    display: "block",
                  }
                : { width: "100%", aspectRatio: "16 / 9", border: 0, display: "block" }
            }
          />
          {isDeck && isFullscreen && (
            // Click-to-advance overlay sits on top of the iframe during
            // present mode. The iframe captures its own clicks, so without
            // this overlay the only way to advance is the keyboard.
            <button
              type="button"
              aria-label="Next slide"
              onClick={advanceInPresent}
              style={{
                position: "absolute",
                inset: 0,
                background: "transparent",
                border: 0,
                cursor: "pointer",
                padding: 0,
                margin: 0,
                color: "transparent",
              }}
            >
              Next
            </button>
          )}
        </div>
        {isDeck && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 12,
              padding: "8px 0",
              userSelect: "none",
            }}
          >
            <button
              type="button"
              onClick={() => setActiveSlide((s) => Math.max(0, s - 1))}
              disabled={activeSlide === 0}
              aria-label="Previous slide"
              style={{
                padding: "4px 10px",
                borderRadius: 6,
                border: "1px solid var(--border, #ddd)",
                background: "var(--surface, #fff)",
                cursor: activeSlide === 0 ? "not-allowed" : "pointer",
                opacity: activeSlide === 0 ? 0.5 : 1,
              }}
            >
              ‹
            </button>
            <span
              style={{
                fontVariantNumeric: "tabular-nums",
                fontSize: 13,
                minWidth: 60,
                textAlign: "center",
              }}
            >
              {activeSlide + 1} / {slideCount}
            </span>
            <button
              type="button"
              onClick={() => setActiveSlide((s) => Math.min(slideCount - 1, s + 1))}
              disabled={activeSlide >= slideCount - 1}
              aria-label="Next slide"
              style={{
                padding: "4px 10px",
                borderRadius: 6,
                border: "1px solid var(--border, #ddd)",
                background: "var(--surface, #fff)",
                cursor: activeSlide >= slideCount - 1 ? "not-allowed" : "pointer",
                opacity: activeSlide >= slideCount - 1 ? 0.5 : 1,
              }}
            >
              ›
            </button>
            <button
              type="button"
              onClick={enterPresent}
              aria-label="Present (F)"
              title="Present (F)"
              style={{
                padding: "4px 10px",
                borderRadius: 6,
                border: "1px solid var(--border, #ddd)",
                background: "var(--surface, #fff)",
                cursor: "pointer",
                marginLeft: 8,
                fontSize: 13,
              }}
            >
              Present
            </button>
          </div>
        )}
        {isDeck && slideCount > 1 && (
          // Progress bar: one clickable segment per slide. Filled segments
          // are slides we've reached or passed; the active segment is
          // accented. Doubles as a jump-to.
          <div
            style={{
              display: "flex",
              gap: 2,
              padding: "0 0 12px",
              userSelect: "none",
            }}
            aria-label="Slide progress"
          >
            {Array.from({ length: slideCount }, (_, i) => {
              const isActive = i === activeSlide;
              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => setActiveSlide(i)}
                  aria-label={`Jump to slide ${i + 1}`}
                  title={`Slide ${i + 1} of ${slideCount}`}
                  style={{
                    flex: 1,
                    height: 4,
                    border: 0,
                    padding: 0,
                    cursor: "pointer",
                    background: isActive
                      ? "var(--accent, #1a73e8)"
                      : i < activeSlide
                        ? "var(--accent-muted, rgba(26,115,232,.35))"
                        : "var(--border, #ddd)",
                    borderRadius: 2,
                  }}
                />
              );
            })}
          </div>
        )}
      </div>
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
//
// Beyond the original resize role, the bootstrap also bridges:
//   - selection changes (to enable the parent's "Comment" button),
//   - wrap requests (parent → iframe → re-serialize HTML back),
//   - click on a `[data-comment-id]` span (focus the thread in the sidebar),
//   - link clicks when the parent opts into routing them,
//   - active thread highlight class,
//   - edit mode: toggles `contenteditable` on body and debounces the
//     "current HTML" round-trip so the parent can save while the user types.
// 'app' (dashboard) pages run author JS inside the sandbox. We inject, at the
// very top of <head> (before any author script runs):
//   1. a CSP egress-lock — the script may read/write the stash data API but
//      can't send data anywhere else, so even agent-authored JS can't exfiltrate;
//   2. for an owner-viewed dashboard, a `window.stash` client bound to the
//      short-lived read token. Public renders get the CSP but no token.
// The page is opaque-origin, so the API must be an absolute URL (apiOrigin).
function injectAppShell(
  html: string,
  apiOrigin: string,
  dashboard: { token: string; workspaceId: string; apiBase: string } | null,
): string {
  const csp =
    `<meta http-equiv="Content-Security-Policy" content="` +
    `default-src 'none'; ` +
    `script-src 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com https://cdnjs.cloudflare.com https://cdn.tailwindcss.com; ` +
    `style-src 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com https://cdnjs.cloudflare.com https://fonts.googleapis.com; ` +
    `font-src data: https://fonts.gstatic.com https://cdn.jsdelivr.net; ` +
    `img-src 'self' data: ${apiOrigin}; ` +
    `connect-src ${apiOrigin};">`;
  let head = csp;
  if (dashboard) {
    const cfg = JSON.stringify(dashboard);
    head +=
      `<script>(function(){var d=${cfg};window.stash={` +
      `token:d.token,workspaceId:d.workspaceId,apiBase:d.apiBase,` +
      `rest:function(path,opts){opts=opts||{};` +
      `var h=Object.assign({},opts.headers,{Authorization:"Bearer "+d.token});` +
      `return fetch(d.apiBase+"/rest/v1/"+path,Object.assign({},opts,{headers:h}));}};})();</script>`;
  }
  if (/<head[^>]*>/i.test(html)) return html.replace(/<head[^>]*>/i, (m) => m + head);
  if (/<html[^>]*>/i.test(html)) return html.replace(/<html[^>]*>/i, (m) => m + head);
  return head + html;
}

function injectResizeBootstrap(
  html: string,
  channel: string,
  bridgeLinks: boolean,
): string {
  // Defensive: a previous save round-trip may have left our bootstrap script
  // or comment-css style tag embedded in `html`. Strip any prior copies so the
  // iframe starts with exactly one fresh bootstrap and doesn't accumulate them.
  const cleaned = html
    .replace(/<script\s+id=["']__stash_resize_script__["'][\s\S]*?<\/script>/gi, "")
    .replace(/<style\s+id=["']__stash_comments_css__["'][\s\S]*?<\/style>/gi, "");
  const script = `<script id="__stash_resize_script__">(function(){
    var c=${JSON.stringify(channel)};
    var BRIDGE_LINKS=${bridgeLinks ? "true" : "false"};
    // Slide-deck HTML (responsive layout with section.slide elements +
    // .slide{display:none}.slide.active{display:flex} styling) only renders
    // one slide at a time. In edit mode we override that so every slide
    // becomes visible and editable; without this the user can only edit the
    // single currently-active slide.
    var COMMENT_HIGHLIGHT_CSS = "[data-comment-id]{background:rgba(254,240,138,.45);cursor:pointer;}[data-comment-id].is-active{background:rgba(250,204,21,.7);outline:1px solid #ca8a04;}body[contenteditable=\\"true\\"]{outline:2px dashed rgba(59,130,246,.5);outline-offset:-4px;}body[contenteditable=\\"true\\"] *{cursor:text;}body[contenteditable=\\"true\\"] section.slide{position:relative !important;inset:auto !important;margin-bottom:24px !important;}";
    var editable=false;
    var mutateTimer=null;
    function post(o){parent.postMessage(Object.assign({channel:c},o),"*");}
    function postResize(){
      var h=Math.max(
        document.documentElement.scrollHeight,
        document.body ? document.body.scrollHeight : 0
      );
      post({type:"skill:resize",height:h});
      reportAnchorTops();
    }
    function reportAnchorTops(){
      var anchorTops={};
      var nodes=document.querySelectorAll("[data-comment-id]");
      for(var i=0;i<nodes.length;i++){
        var el=nodes[i];
        var id=el.getAttribute("data-comment-id");
        if(!id) continue;
        var rects=el.getClientRects();
        var rect=rects[0]||el.getBoundingClientRect();
        var top=Math.max(0,Math.round(rect.top));
        if(anchorTops[id]===undefined || top<anchorTops[id]) anchorTops[id]=top;
      }
      post({type:"skill:anchor-tops",anchorTops:anchorTops});
    }
    function injectStyle(){
      if(document.getElementById("__stash_comments_css__")) return;
      var s=document.createElement("style");
      s.id="__stash_comments_css__";
      s.textContent=COMMENT_HIGHLIGHT_CSS;
      (document.head||document.documentElement).appendChild(s);
    }
    // Serialize the document without our injected bootstrap or the edit-only
    // body attributes. Without this, entering edit mode sets contenteditable +
    // spellcheck on body, and the debounced save would bake those into the
    // persisted content_html — so every later viewer would load an editable
    // page with the dashed edit outline. Strip them on every serialize.
    function serializeClean(){
      var clone=document.documentElement.cloneNode(true);
      var junk=clone.querySelectorAll("#__stash_comments_css__, #__stash_resize_script__");
      for(var i=0;i<junk.length;i++){
        if(junk[i].parentNode) junk[i].parentNode.removeChild(junk[i]);
      }
      var cb=clone.querySelector("body");
      if(cb){
        cb.removeAttribute("contenteditable");
        cb.removeAttribute("spellcheck");
      }
      return clone.outerHTML;
    }
    function reportSelection(){
      // While editing, selections are caret moves — don't surface them
      // as comment targets.
      if(editable){
        post({type:"skill:selection",cleared:true});
        return;
      }
      var sel=window.getSelection();
      if(!sel||sel.rangeCount===0||sel.isCollapsed){
        post({type:"skill:selection",cleared:true});
        return;
      }
      var range=sel.getRangeAt(0);
      var text=sel.toString();
      if(!text||!text.trim()){
        post({type:"skill:selection",cleared:true});
        return;
      }
      var rects=range.getClientRects();
      var last=rects[rects.length-1]||range.getBoundingClientRect();
      // 32-char context window on each side, lifted from the rendered text.
      var pre=document.body?document.body.innerText:"";
      var idx=pre.indexOf(text);
      var prefix="",suffix="";
      if(idx>=0){
        prefix=pre.slice(Math.max(0,idx-32),idx);
        suffix=pre.slice(idx+text.length,idx+text.length+32);
      }
      post({
        type:"skill:selection",
        quoted_text:text,
        prefix:prefix,
        suffix:suffix,
        rect:{top:last.top,left:last.left,right:last.right,bottom:last.bottom}
      });
    }
    function wrapSelection(id){
      var sel=window.getSelection();
      if(!sel||sel.rangeCount===0||sel.isCollapsed){
        post({type:"stash:html-mutated",html:serializeClean()});
        return;
      }
      var range=sel.getRangeAt(0);
      var span=document.createElement("span");
      span.setAttribute("data-comment-id",id);
      try{
        range.surroundContents(span);
      }catch(e){
        // surroundContents throws when the range spans partial element
        // boundaries — fall back to extracting + appending.
        var frag=range.extractContents();
        span.appendChild(frag);
        range.insertNode(span);
      }
      sel.removeAllRanges();
      reportAnchorTops();
      post({type:"stash:html-mutated",html:serializeClean()});
    }
    function unwrap(id){
      var match=document.querySelectorAll('[data-comment-id="'+id+'"]');
      if(match.length===0) return;
      for(var i=0;i<match.length;i++){
        var el=match[i];
        var parent=el.parentNode;
        if(!parent) continue;
        while(el.firstChild) parent.insertBefore(el.firstChild,el);
        parent.removeChild(el);
      }
      reportAnchorTops();
      post({type:"stash:html-mutated",html:serializeClean()});
    }
    function applyActive(id){
      var prev=document.querySelectorAll("[data-comment-id].is-active");
      for(var i=0;i<prev.length;i++) prev[i].classList.remove("is-active");
      if(!id) return;
      var match=document.querySelectorAll('[data-comment-id="'+id+'"]');
      for(var j=0;j<match.length;j++){
        match[j].classList.add("is-active");
        if(j===0) match[j].scrollIntoView({block:"center",behavior:"smooth"});
      }
    }
    function setEditable(enabled){
      editable=!!enabled;
      if(!document.body) return;
      if(editable){
        document.body.setAttribute("contenteditable","true");
        document.body.setAttribute("spellcheck","true");
      } else {
        document.body.removeAttribute("contenteditable");
        document.body.removeAttribute("spellcheck");
        // Flush any pending debounced edit before leaving edit mode so we
        // don't drop the last 500ms of typing.
        if(mutateTimer){
          clearTimeout(mutateTimer);
          mutateTimer=null;
          post({type:"stash:html-mutated",html:serializeClean()});
        }
      }
    }
    function scheduleMutate(){
      if(!editable) return;
      if(mutateTimer) clearTimeout(mutateTimer);
      mutateTimer=setTimeout(function(){
        mutateTimer=null;
        post({type:"stash:html-mutated",html:serializeClean()});
      },500);
    }
    // Heal pages saved by an older build that baked contenteditable/spellcheck
    // into content_html: the page loads in view mode, so strip the edit-only
    // attributes up front instead of relying on a set-editable(false) message
    // that can race ahead of this listener and be dropped.
    if(document.body){
      document.body.removeAttribute("contenteditable");
      document.body.removeAttribute("spellcheck");
    }
    injectStyle();
    new ResizeObserver(postResize).observe(document.documentElement);
    if(document.body) new ResizeObserver(postResize).observe(document.body);
    document.addEventListener("selectionchange",reportSelection);
    document.addEventListener("input",scheduleMutate);
    document.addEventListener("click",function(e){
      // Comment-anchor click navigation only applies in view mode; in edit
      // mode a click on a span is the user placing their caret.
      if(editable) return;
      var t=e.target;
      while(t && t!==document){
        if(t.getAttribute && t.getAttribute("data-comment-id")){
          e.preventDefault();
          post({type:"skill:thread-click",id:t.getAttribute("data-comment-id")});
          return;
        }
        t=t.parentNode;
      }
      post({type:"skill:thread-deselect"});
      if(!BRIDGE_LINKS) return;
      var a=e.target;
      while(a && a!==document){
        if(a.tagName && String(a.tagName).toLowerCase()==="a"){
          var href=a.getAttribute("href");
          if(href){
            if(href.charAt(0)==="#") return;
            e.preventDefault();
            post({type:"skill:navigate",href:href});
          }
          return;
        }
        a=a.parentNode;
      }
    });
    window.addEventListener("message",function(e){
      var d=e.data;
      if(!d || d.channel!==c) return;
      if(d.type==="skill:probe") postResize();
      else if(d.type==="skill:wrap") wrapSelection(String(d.id||""));
      else if(d.type==="skill:unwrap") unwrap(String(d.id||""));
      else if(d.type==="skill:active") applyActive(d.id||null);
      else if(d.type==="skill:set-editable") setEditable(d.enabled);
    });
    postResize();
  })();</script>`;
  if (/<\/body>/i.test(cleaned)) return cleaned.replace(/<\/body>/i, `${script}</body>`);
  return cleaned + script;
}

// Helper: count `data-comment-id` values present in saved HTML. Used by
// the page route to reconcile orphans on each save.
export function extractCommentIdsFromHtml(html: string): string[] {
  const ids: string[] = [];
  const re = /data-comment-id="([^"]+)"/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(html)) !== null) ids.push(m[1]);
  return Array.from(new Set(ids));
}

// Bootstrap injected into fixed-aspect slide decks. Listens for
// `stash:slide-goto` from the parent and shows only that section.
// Pages with zero `<section class="slide">` elements bypass this path.
function injectSlideDeckBootstrap(html: string, channel: string): string {
  // Defensive: a previous save round-trip may have left our bootstrap script
  // or style tag embedded in `html`. Strip any prior copies so the iframe
  // starts with exactly one fresh bootstrap.
  const cleaned = html
    .replace(/<script\s+id=["']__stash_slide_script__["'][\s\S]*?<\/script>/gi, "")
    .replace(/<style\s+id=["']__stash_slide_css__["'][\s\S]*?<\/style>/gi, "");
  const script = `<script id="__stash_slide_script__">(function(){
    // Idempotency: the bootstrap script gets re-injected on every srcDoc
    // build, and the iframe's saved HTML round-trip may already contain a
    // previous copy. Exit on the second copy so we don't double-up the
    // message handlers.
    if(window.__stash_slide_bootstrapped__) return;
    window.__stash_slide_bootstrapped__=true;
    var c=${JSON.stringify(channel)};
    var editable=false;
    var currentIdx=0;
    // Strip any inline body state left over from a previous edit session.
    // applyCanvasZoom sets body.style.zoom, and edit mode toggles
    // contenteditable + spellcheck on body — earlier versions of
    // serializeClean baked those into content_html on save. Without this
    // strip, a saved zoom=0.4 leaves the body rendering at ~835px in a
    // 1920px export viewport, with body bg filling the rest. serializeClean
    // also strips on save now, but legacy decks already have the pollution.
    (function stripBodyState(){
      if(!document.body) return;
      document.body.style.removeProperty('zoom');
      if(document.body.getAttribute('style')==='') document.body.removeAttribute('style');
      document.body.removeAttribute('contenteditable');
      document.body.removeAttribute('spellcheck');
    })();
    // Canvas-enforcing CSS: every slide is a 1920x1080 box that clips its own
    // overflow. Body is sized to 1920px so the slide design space is fixed;
    // applyCanvasZoom() (below) sets document.body.style.zoom so the visual
    // shrinks to the iframe width. CSS zoom:calc(100vw / 1920) evaluates
    // to 1 in Chromium, so we drive zoom from JS instead.
    var CANVAS_CSS = "html,body{margin:0;padding:0;overflow-x:hidden;}body{width:1920px;}section.slide{width:1920px;height:1080px;overflow:hidden;position:relative;box-sizing:border-box;display:block;}";
    function applyCanvasZoom(){
      if(!document.body) return;
      // During export (Playwright @ 1920 viewport) ratio is 1 — pixel-perfect
      // with author intent. In the viewer's responsive iframe ratio < 1.
      var ratio = window.innerWidth / 1920;
      document.body.style.zoom = ratio > 0 ? String(ratio) : "1";
    }
    window.addEventListener('resize', applyCanvasZoom);
    // Visual feedback for edit mode: dashed outline on the body, text caret
    // on all descendants, and let slides flow normally so the user can scroll
    // and click between them.
    // Edit mode just adds a dashed outline + reflows the slide stack so all
    // slides are visible at once. Don't override the section's display
    // property here — clobbering it to display:flex !important rearranges
    // children that depend on the section's natural block layout (or the
    // agent's inline flex direction). Visibility is controlled by clearing
    // the inline style.display in applyIndex().
    var EDIT_CSS = "body[contenteditable=\\"true\\"]{outline:2px dashed rgba(59,130,246,.5);outline-offset:-4px;}body[contenteditable=\\"true\\"] *{cursor:text;}body[contenteditable=\\"true\\"] section.slide{position:relative !important;inset:auto !important;margin-bottom:24px !important;}";
    (function injectStyle(){
      if(document.getElementById("__stash_slide_css__")) return;
      var s=document.createElement('style');
      s.id="__stash_slide_css__";
      // Canvas rules first so any agent rules in the document can override
      // by specificity or document order. Edit rules use !important so they
      // win where needed.
      s.textContent=CANVAS_CSS+EDIT_CSS;
      (document.head||document.documentElement).appendChild(s);
    })();
    applyCanvasZoom();
    function applyIndex(idx){
      var slides=document.querySelectorAll('body > section.slide');
      if(!slides.length) return;
      currentIdx=Math.max(0, Math.min(slides.length-1, idx|0));
      // In edit mode every slide is rendered in a vertical flow so the user
      // can scroll between them. Clearing the inline display lets each
      // section fall back to its natural CSS display. Then scroll the
      // active slide into view so clicking prev/next actually moves the
      // viewport — without this, the counter updates but nothing visible
      // happens.
      if(editable){
        for(var k=0;k<slides.length;k++) slides[k].style.display='';
        var target=slides[currentIdx];
        if(target && typeof target.scrollIntoView==='function'){
          target.scrollIntoView({block:'start',behavior:'smooth'});
        }
        return;
      }
      for(var k=0;k<slides.length;k++){
        slides[k].style.display = (k===currentIdx) ? '' : 'none';
      }
    }
    var mutateTimer=null;
    function post(o){parent.postMessage(Object.assign({channel:c},o),'*');}
    // Serialize the document without our injected bootstrap so saved HTML
    // doesn't accumulate copies of the script/style on every edit. Also
    // strip the bits that only exist while the bootstrap is live:
    //   - body.style.zoom set by applyCanvasZoom — if it bakes into the
    //     saved html the export renders the body shrunk to ~835px on a
    //     1920px viewport, leaving the rest of the slide as body bg.
    //   - contenteditable / spellcheck on body — set when entering edit
    //     mode and not meaningful in the persisted page.
    function serializeClean(){
      var clone=document.documentElement.cloneNode(true);
      var nodes=clone.querySelectorAll('#__stash_slide_css__, #__stash_slide_script__');
      for(var i=0;i<nodes.length;i++){
        var n=nodes[i];
        if(n.parentNode) n.parentNode.removeChild(n);
      }
      var cb=clone.querySelector('body');
      if(cb){
        cb.style.removeProperty('zoom');
        if(cb.getAttribute('style')==='') cb.removeAttribute('style');
        cb.removeAttribute('contenteditable');
        cb.removeAttribute('spellcheck');
      }
      return clone.outerHTML;
    }
    function scheduleMutate(){
      if(!editable) return;
      if(mutateTimer) clearTimeout(mutateTimer);
      mutateTimer=setTimeout(function(){
        mutateTimer=null;
        post({type:'stash:html-mutated',html:serializeClean()});
      },500);
    }
    document.addEventListener('input',scheduleMutate);
    window.addEventListener('message', function(e){
      var d=e.data;
      if(!d||typeof d!=='object'||d.channel!==c) return;
      if(d.type==='stash:slide-goto' && typeof d.index==='number') applyIndex(d.index);
      else if(d.type==='skill:set-editable'){
        editable=!!d.enabled;
        if(document.body){
          if(editable){
            document.body.setAttribute('contenteditable','true');
            document.body.setAttribute('spellcheck','true');
          } else {
            document.body.removeAttribute('contenteditable');
            document.body.removeAttribute('spellcheck');
            // Flush any pending edit before leaving edit mode.
            if(mutateTimer){
              clearTimeout(mutateTimer);
              mutateTimer=null;
              post({type:'stash:html-mutated',html:serializeClean()});
            }
          }
        }
        applyIndex(currentIdx);
      }
    });
    applyIndex(0);
  })();</script>`;
  if (/<\/body\s*>/i.test(cleaned)) return cleaned.replace(/<\/body\s*>/i, script + "</body>");
  return cleaned + script;
}
