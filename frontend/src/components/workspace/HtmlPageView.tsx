"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";

export type HtmlLayout = "responsive" | "fixed-aspect";

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
  onActivateThread?: (threadId: string) => void;
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
  pendingWrapId,
  onWrapComplete,
  onHtmlMutated,
  onNavigateLink,
  activeThreadId,
  stripCommentToken,
  editable = false,
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
    if (layout === "responsive")
      return injectResizeBootstrap(initialHtml, channel, Boolean(onNavigateLink));
    if (isDeck) return injectSlideDeckBootstrap(initialHtml, channel);
    return initialHtml;
  }, [layout, channel, initialHtml, isDeck, onNavigateLink]);

  useEffect(() => {
    function onMessage(e: MessageEvent) {
      const data = e.data;
      if (!data || typeof data !== "object" || data.channel !== channel) return;
      if (data.type === "stash:resize" && typeof data.height === "number") {
        if (layout === "responsive") setHeight(Math.max(0, Math.ceil(data.height)));
        return;
      }
      if (data.type === "stash:selection") {
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
      if (data.type === "stash:thread-click" && typeof data.id === "string") {
        onActivateThread?.(data.id);
        return;
      }
      if (data.type === "stash:html-mutated" && typeof data.html === "string") {
        onHtmlMutated?.(data.html);
        onWrapComplete?.();
        return;
      }
      if (data.type === "stash:navigate" && typeof data.href === "string") {
        onNavigateLink?.(data.href);
        return;
      }
    }
    window.addEventListener("message", onMessage);
    iframeRef.current?.contentWindow?.postMessage(
      { type: "stash:probe", channel },
      "*",
    );
    return () => window.removeEventListener("message", onMessage);
  }, [
    layout,
    channel,
    onSelection,
    onActivateThread,
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
      { type: "stash:wrap", channel, id: pendingWrapId },
      "*",
    );
  }, [pendingWrapId, channel]);

  // Push active thread id to the iframe so it can style the matching span.
  useEffect(() => {
    iframeRef.current?.contentWindow?.postMessage(
      { type: "stash:active", channel, id: activeThreadId ?? null },
      "*",
    );
  }, [activeThreadId, channel]);

  // Strip the inline `<span data-comment-id>` wrapper for a just-deleted
  // thread. The iframe unwraps and posts back the new HTML, which the
  // parent saves via `onHtmlMutated`.
  useEffect(() => {
    if (!stripCommentToken) return;
    iframeRef.current?.contentWindow?.postMessage(
      { type: "stash:unwrap", channel, id: stripCommentToken.id },
      "*",
    );
  }, [stripCommentToken, channel]);

  // Push edit-mode to the iframe whenever it changes.
  useEffect(() => {
    iframeRef.current?.contentWindow?.postMessage(
      { type: "stash:set-editable", channel, enabled: editable },
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
      { type: "stash:probe", channel },
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
function injectResizeBootstrap(
  html: string,
  channel: string,
  bridgeLinks: boolean,
): string {
  const script = `<script>(function(){
    var c=${JSON.stringify(channel)};
    var BRIDGE_LINKS=${bridgeLinks ? "true" : "false"};
    // Slide-deck HTML (responsive layout with section.slide elements +
    // .slide{display:none}.slide.active{display:flex} styling) only renders
    // one slide at a time. In edit mode we override that so every slide
    // becomes visible and editable; without this the user can only edit the
    // single currently-active slide.
    var COMMENT_HIGHLIGHT_CSS = "[data-comment-id]{background:rgba(254,240,138,.45);cursor:pointer;}[data-comment-id].is-active{background:rgba(250,204,21,.7);outline:1px solid #ca8a04;}body[contenteditable=\\"true\\"]{outline:2px dashed rgba(59,130,246,.5);outline-offset:-4px;}body[contenteditable=\\"true\\"] *{cursor:text;}body[contenteditable=\\"true\\"] section.slide{display:flex !important;position:relative !important;inset:auto !important;margin-bottom:24px !important;}";
    var editable=false;
    var mutateTimer=null;
    function post(o){parent.postMessage(Object.assign({channel:c},o),"*");}
    function postResize(){
      var h=Math.max(
        document.documentElement.scrollHeight,
        document.body ? document.body.scrollHeight : 0
      );
      post({type:"stash:resize",height:h});
    }
    function injectStyle(){
      if(document.getElementById("__stash_comments_css__")) return;
      var s=document.createElement("style");
      s.id="__stash_comments_css__";
      s.textContent=COMMENT_HIGHLIGHT_CSS;
      (document.head||document.documentElement).appendChild(s);
    }
    function reportSelection(){
      // While editing, selections are caret moves — don't surface them
      // as comment targets.
      if(editable){
        post({type:"stash:selection",cleared:true});
        return;
      }
      var sel=window.getSelection();
      if(!sel||sel.rangeCount===0||sel.isCollapsed){
        post({type:"stash:selection",cleared:true});
        return;
      }
      var range=sel.getRangeAt(0);
      var text=sel.toString();
      if(!text||!text.trim()){
        post({type:"stash:selection",cleared:true});
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
        type:"stash:selection",
        quoted_text:text,
        prefix:prefix,
        suffix:suffix,
        rect:{top:last.top,left:last.left,right:last.right,bottom:last.bottom}
      });
    }
    function wrapSelection(id){
      var sel=window.getSelection();
      if(!sel||sel.rangeCount===0||sel.isCollapsed){
        post({type:"stash:html-mutated",html:document.documentElement.outerHTML});
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
      post({type:"stash:html-mutated",html:document.documentElement.outerHTML});
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
      post({type:"stash:html-mutated",html:document.documentElement.outerHTML});
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
          post({type:"stash:html-mutated",html:document.documentElement.outerHTML});
        }
      }
    }
    function scheduleMutate(){
      if(!editable) return;
      if(mutateTimer) clearTimeout(mutateTimer);
      mutateTimer=setTimeout(function(){
        mutateTimer=null;
        post({type:"stash:html-mutated",html:document.documentElement.outerHTML});
      },500);
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
          post({type:"stash:thread-click",id:t.getAttribute("data-comment-id")});
          return;
        }
        t=t.parentNode;
      }
      if(!BRIDGE_LINKS) return;
      var a=e.target;
      while(a && a!==document){
        if(a.tagName && String(a.tagName).toLowerCase()==="a"){
          var href=a.getAttribute("href");
          if(href){
            if(href.charAt(0)==="#") return;
            e.preventDefault();
            post({type:"stash:navigate",href:href});
          }
          return;
        }
        a=a.parentNode;
      }
    });
    window.addEventListener("message",function(e){
      var d=e.data;
      if(!d || d.channel!==c) return;
      if(d.type==="stash:probe") postResize();
      else if(d.type==="stash:wrap") wrapSelection(String(d.id||""));
      else if(d.type==="stash:unwrap") unwrap(String(d.id||""));
      else if(d.type==="stash:active") applyActive(d.id||null);
      else if(d.type==="stash:set-editable") setEditable(d.enabled);
    });
    postResize();
  })();</script>`;
  if (/<\/body>/i.test(html)) return html.replace(/<\/body>/i, `${script}</body>`);
  return html + script;
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
  const script = `<script>(function(){
    var c=${JSON.stringify(channel)};
    var editable=false;
    var currentIdx=0;
    // Visual feedback for edit mode: dashed outline on the body, text caret
    // on all descendants, and let slides flow normally so the user can scroll
    // and click between them.
    var EDIT_CSS = "body[contenteditable=\\"true\\"]{outline:2px dashed rgba(59,130,246,.5);outline-offset:-4px;}body[contenteditable=\\"true\\"] *{cursor:text;}body[contenteditable=\\"true\\"] section.slide{display:flex !important;position:relative !important;inset:auto !important;margin-bottom:24px !important;}";
    (function injectStyle(){
      var s=document.createElement('style');
      s.textContent=EDIT_CSS;
      (document.head||document.documentElement).appendChild(s);
    })();
    function applyIndex(idx){
      var slides=document.querySelectorAll('body > section.slide');
      if(!slides.length) return;
      currentIdx=Math.max(0, Math.min(slides.length-1, idx|0));
      // In edit mode, show every slide so the user can edit all of them.
      // The deck nav still tracks currentIdx for when edit mode is exited.
      if(editable){
        for(var k=0;k<slides.length;k++) slides[k].style.display='';
        return;
      }
      for(var k=0;k<slides.length;k++){
        slides[k].style.display = (k===currentIdx) ? '' : 'none';
      }
    }
    var mutateTimer=null;
    function post(o){parent.postMessage(Object.assign({channel:c},o),'*');}
    function scheduleMutate(){
      if(!editable) return;
      if(mutateTimer) clearTimeout(mutateTimer);
      mutateTimer=setTimeout(function(){
        mutateTimer=null;
        post({type:'stash:html-mutated',html:document.documentElement.outerHTML});
      },500);
    }
    document.addEventListener('input',scheduleMutate);
    window.addEventListener('message', function(e){
      var d=e.data;
      if(!d||typeof d!=='object'||d.channel!==c) return;
      if(d.type==='stash:slide-goto' && typeof d.index==='number') applyIndex(d.index);
      else if(d.type==='stash:set-editable'){
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
              post({type:'stash:html-mutated',html:document.documentElement.outerHTML});
            }
          }
        }
        applyIndex(currentIdx);
      }
    });
    applyIndex(0);
  })();</script>`;
  if (/<\/body\s*>/i.test(html)) return html.replace(/<\/body\s*>/i, script + "</body>");
  return html + script;
}
