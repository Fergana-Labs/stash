"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";

export type HtmlSelectionInfo = {
  quoted_text: string;
  prefix: string;
  suffix: string;
  /** Bounding rect of the selection's last line, in iframe viewport
   *  coords — the parent anchors the Comment pill to it. */
  rect: { top: number; left: number; right: number; bottom: number };
};

type Props = {
  html: string;
  title: string;
  /** When true, the iframe's body becomes `contenteditable` and posts
   *  debounced `stash:html-mutated` events as the user types. The iframe
   *  is the source of truth while editable — we don't reflow it from
   *  `html` prop changes, so the caret survives the save round-trip. */
  editable?: boolean;
  onHtmlMutated?: (nextHtml: string) => void;
  /** Surfaces text selections inside the iframe so the parent can show
   *  a Comment pill anchored to them. */
  onSelection?: (info: HtmlSelectionInfo | null) => void;
  /** Comment anchors to highlight: the iframe finds each quoted string
   *  in its rendered text and wraps it in a [data-comment-id] span. */
  highlights?: { id: string; quoted: string }[];
};

// Minimal port of the product app's HtmlPageView: sandboxed srcDoc iframe
// with a postMessage bootstrap for height auto-resize and in-place editing.
// `sandbox="allow-scripts"` (no allow-same-origin) keeps user HTML in an
// opaque origin — scripts run but can't touch our cookies or DOM.
export default function HtmlFrame({
  html,
  title,
  editable = false,
  onHtmlMutated,
  onSelection,
  highlights,
}: Props) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [height, setHeight] = useState<number | null>(null);
  const channel = `stash-resize-${useId()}`;

  // The iframe's DOM is authoritative for its lifetime: pin srcDoc to the
  // first `html` we see so edit-mode saves don't reload the iframe and
  // trash the caret. Remount (key change) to load different content.
  const [initialHtml] = useState(html);
  const srcDoc = useMemo(() => injectBootstrap(initialHtml, channel), [initialHtml, channel]);

  useEffect(() => {
    function onMessage(e: MessageEvent) {
      const data = e.data;
      if (!data || typeof data !== "object" || data.channel !== channel) return;
      if (data.type === "skill:resize" && typeof data.height === "number") {
        setHeight(Math.max(0, Math.ceil(data.height)));
        return;
      }
      if (data.type === "stash:html-mutated" && typeof data.html === "string") {
        onHtmlMutated?.(data.html);
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
      }
    }
    window.addEventListener("message", onMessage);
    iframeRef.current?.contentWindow?.postMessage({ type: "skill:probe", channel }, "*");
    return () => window.removeEventListener("message", onMessage);
  }, [channel, onHtmlMutated, onSelection]);

  useEffect(() => {
    iframeRef.current?.contentWindow?.postMessage(
      { type: "skill:set-editable", channel, enabled: editable },
      "*",
    );
  }, [editable, channel]);

  useEffect(() => {
    if (!highlights?.length) return;
    iframeRef.current?.contentWindow?.postMessage(
      { type: "stash:highlight", channel, items: highlights },
      "*",
    );
  }, [highlights, channel]);

  function onIframeLoad() {
    iframeRef.current?.contentWindow?.postMessage({ type: "skill:probe", channel }, "*");
    if (editable) {
      iframeRef.current?.contentWindow?.postMessage(
        { type: "skill:set-editable", channel, enabled: true },
        "*",
      );
    }
    if (highlights?.length) {
      iframeRef.current?.contentWindow?.postMessage(
        { type: "stash:highlight", channel, items: highlights },
        "*",
      );
    }
  }

  return (
    <iframe
      ref={iframeRef}
      srcDoc={srcDoc}
      sandbox="allow-scripts"
      title={title}
      onLoad={onIframeLoad}
      style={{ width: "100%", height: height ?? 200, border: 0, display: "block" }}
    />
  );
}

// Appended just before </body>. Lives inside the sandbox like any other
// script in the document — adding it doesn't widen the trust boundary.
// Bridges: scrollHeight reports (resize), and edit mode (contenteditable
// on body + debounced clean-serialized HTML round-trips).
function injectBootstrap(html: string, channel: string): string {
  // A previous save round-trip may have left our bootstrap embedded in
  // `html` — strip prior copies so the iframe starts with exactly one.
  const cleaned = html.replace(
    /<script\s+id=["']__stash_resize_script__["'][\s\S]*?<\/script>/gi,
    "",
  );
  const script = `<script id="__stash_resize_script__">(function(){
    var c=${JSON.stringify(channel)};
    var EDIT_CSS = "body[contenteditable=\\"true\\"]{outline:2px dashed rgba(59,130,246,.5);outline-offset:-4px;}body[contenteditable=\\"true\\"] *{cursor:text;}[data-comment-id]{background:rgba(254,240,138,.45);border-radius:2px;}";
    var editable=false;
    var mutateTimer=null;
    function post(o){parent.postMessage(Object.assign({channel:c},o),"*");}
    function postResize(){
      var h=Math.max(
        document.documentElement.scrollHeight,
        document.body ? document.body.scrollHeight : 0
      );
      post({type:"skill:resize",height:h});
    }
    function injectStyle(){
      if(document.getElementById("__stash_edit_css__")) return;
      var s=document.createElement("style");
      s.id="__stash_edit_css__";
      s.textContent=EDIT_CSS;
      (document.head||document.documentElement).appendChild(s);
    }
    // Serialize without our bootstrap or the edit-only body attributes so
    // they never bake into the saved HTML.
    function serializeClean(){
      var clone=document.documentElement.cloneNode(true);
      var junk=clone.querySelectorAll("#__stash_edit_css__, #__stash_resize_script__");
      for(var i=0;i<junk.length;i++){
        if(junk[i].parentNode) junk[i].parentNode.removeChild(junk[i]);
      }
      // Comment highlights are presentation-only — unwrap them so they
      // never bake into the saved HTML.
      var marks=clone.querySelectorAll("[data-comment-id]");
      for(var j=0;j<marks.length;j++){
        var m=marks[j];
        var p=m.parentNode;
        if(!p) continue;
        while(m.firstChild) p.insertBefore(m.firstChild,m);
        p.removeChild(m);
      }
      var cb=clone.querySelector("body");
      if(cb){
        cb.removeAttribute("contenteditable");
        cb.removeAttribute("spellcheck");
      }
      return clone.outerHTML;
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
        // Flush any pending debounced edit before leaving edit mode.
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
    function reportSelection(){
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
    // Find each comment's quoted text in the rendered DOM and wrap it in
    // a [data-comment-id] span — highlights are presentation-only and
    // serializeClean's clone never includes them... they live only in the
    // live DOM, recreated on every load.
    function applyHighlights(items){
      for(var i=0;i<items.length;i++){
        var it=items[i];
        if(!it||!it.quoted||!it.id) continue;
        if(document.querySelector('[data-comment-id="'+it.id+'"]')) continue;
        wrapFirst(String(it.quoted),String(it.id));
      }
    }
    function wrapFirst(quoted,id){
      var walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT,null);
      var nodes=[],starts=[],full="";
      var t;
      while((t=walker.nextNode())){starts.push(full.length);nodes.push(t);full+=t.textContent||"";}
      var idx=full.indexOf(quoted);
      if(idx<0) return;
      function loc(pos,isEnd){
        var probe=isEnd?pos-1:pos;
        for(var i=nodes.length-1;i>=0;i--){
          if(starts[i]<=probe) return {node:nodes[i],offset:pos-starts[i]};
        }
        return null;
      }
      var s=loc(idx,false),e=loc(idx+quoted.length,true);
      if(!s||!e) return;
      var range=document.createRange();
      range.setStart(s.node,s.offset);
      range.setEnd(e.node,e.offset);
      var span=document.createElement("span");
      span.setAttribute("data-comment-id",id);
      try{range.surroundContents(span);}
      catch(err){span.appendChild(range.extractContents());range.insertNode(span);}
    }
    if(document.body){
      document.body.removeAttribute("contenteditable");
      document.body.removeAttribute("spellcheck");
    }
    injectStyle();
    new ResizeObserver(postResize).observe(document.documentElement);
    if(document.body) new ResizeObserver(postResize).observe(document.body);
    document.addEventListener("input",scheduleMutate);
    document.addEventListener("selectionchange",reportSelection);
    window.addEventListener("message",function(e){
      var d=e.data;
      if(!d || d.channel!==c) return;
      if(d.type==="skill:probe") postResize();
      else if(d.type==="skill:set-editable") setEditable(d.enabled);
      else if(d.type==="stash:highlight") applyHighlights(d.items||[]);
    });
    postResize();
  })();</script>`;
  if (/<\/body>/i.test(cleaned)) return cleaned.replace(/<\/body>/i, `${script}</body>`);
  return cleaned + script;
}
