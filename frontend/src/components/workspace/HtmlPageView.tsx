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
  const [height, setHeight] = useState<number | null>(null);
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

  // Keyboard nav (←/→) when the deck is on screen. We bail when the
  // user is typing somewhere (any input/textarea/contenteditable),
  // otherwise arrow keys would silently steal focus from the comment
  // composer, share modal, page-title editor, etc.
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
      if (e.key === "ArrowRight") {
        setActiveSlide((s) => Math.min(slideCount - 1, s + 1));
      } else if (e.key === "ArrowLeft") {
        setActiveSlide((s) => Math.max(0, s - 1));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isDeck, slideCount]);

  function onIframeLoad() {
    iframeRef.current?.contentWindow?.postMessage(
      { type: "stash:probe", channel },
      "*",
    );
  }

  if (layout === "fixed-aspect") {
    return (
      <div style={{ position: "relative", width: "100%" }}>
        <iframe
          ref={iframeRef}
          srcDoc={srcDoc}
          sandbox="allow-scripts"
          title={title}
          onLoad={onIframeLoad}
          style={{ width: "100%", aspectRatio: "16 / 9", border: 0, display: "block" }}
        />
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
    var EDIT_CSS = "body[contenteditable=\\"true\\"]{outline:2px dashed rgba(59,130,246,.5);outline-offset:-4px;}body[contenteditable=\\"true\\"] *{cursor:text;}body[contenteditable=\\"true\\"] section.slide{display:flex !important;position:relative !important;inset:auto !important;margin-bottom:24px !important;}";
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
    // Serialize the document without our injected bootstrap so saved HTML
    // doesn't accumulate copies of the script/style on every edit.
    function serializeClean(){
      var clone=document.documentElement.cloneNode(true);
      var nodes=clone.querySelectorAll('#__stash_slide_css__, #__stash_slide_script__');
      for(var i=0;i<nodes.length;i++){
        var n=nodes[i];
        if(n.parentNode) n.parentNode.removeChild(n);
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
