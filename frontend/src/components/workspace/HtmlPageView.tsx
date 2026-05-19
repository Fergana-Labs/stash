"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";

export type HtmlLayout = "responsive" | "fixed-aspect";

export type HtmlSelectionInfo = {
  quoted_text: string;
  prefix: string;
  suffix: string;
  /** Viewport coords of the selection end relative to the iframe.
   *  The parent adds the iframe's offset to position UI. */
  endX: number;
  endY: number;
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
  /** Highlight the currently selected thread's anchor span. */
  activeThreadId?: string | null;
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
  activeThreadId,
}: Props) {
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
      if (!data || typeof data !== "object" || data.channel !== channel) return;
      if (data.type === "stash:resize" && typeof data.height === "number") {
        setHeight(Math.max(0, Math.ceil(data.height)));
        return;
      }
      if (data.type === "stash:selection") {
        if (data.cleared) {
          onSelection?.(null);
          return;
        }
        onSelection?.({
          quoted_text: String(data.quoted_text ?? ""),
          prefix: String(data.prefix ?? ""),
          suffix: String(data.suffix ?? ""),
          endX: Number(data.endX ?? 0),
          endY: Number(data.endY ?? 0),
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
    }
    window.addEventListener("message", onMessage);
    iframeRef.current?.contentWindow?.postMessage(
      { type: "stash:probe", channel },
      "*",
    );
    return () => window.removeEventListener("message", onMessage);
  }, [layout, channel, onSelection, onActivateThread, onHtmlMutated, onWrapComplete]);

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
//
// Beyond the original resize role, the bootstrap also bridges:
//   - selection changes (to enable the parent's "Comment" button),
//   - wrap requests (parent → iframe → re-serialize HTML back),
//   - click on a `[data-comment-id]` span (focus the thread in the sidebar),
//   - active thread highlight class.
function injectResizeBootstrap(html: string, channel: string): string {
  const script = `<script>(function(){
    var c=${JSON.stringify(channel)};
    var COMMENT_HIGHLIGHT_CSS = "[data-comment-id]{background:rgba(254,240,138,.45);cursor:pointer;}[data-comment-id].is-active{background:rgba(250,204,21,.7);outline:1px solid #ca8a04;}";
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
        endX:last.right,
        endY:last.bottom
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
    injectStyle();
    new ResizeObserver(postResize).observe(document.documentElement);
    if(document.body) new ResizeObserver(postResize).observe(document.body);
    document.addEventListener("selectionchange",reportSelection);
    document.addEventListener("click",function(e){
      var t=e.target;
      while(t && t!==document){
        if(t.getAttribute && t.getAttribute("data-comment-id")){
          post({type:"stash:thread-click",id:t.getAttribute("data-comment-id")});
          return;
        }
        t=t.parentNode;
      }
    });
    window.addEventListener("message",function(e){
      var d=e.data;
      if(!d || d.channel!==c) return;
      if(d.type==="stash:probe") postResize();
      else if(d.type==="stash:wrap") wrapSelection(String(d.id||""));
      else if(d.type==="stash:active") applyActive(d.id||null);
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
