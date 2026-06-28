"use client";

// HTML canvas — renders an agent-emitted self-contained HTML/CSS/JS fragment
// (the `render_html` tool) in a SANDBOXED iframe. This is the Google-style
// "generative UI for any prompt" path: maximum flexibility, with the iframe
// sandbox as the security boundary.
//
// Security: sandbox="allow-scripts" WITHOUT allow-same-origin → the frame has an
// opaque origin, so its scripts cannot touch the parent DOM, cookies, or storage.
// A strict CSP blocks network/XHR (connect-src 'none'); images allowed only as
// data: or https:. The frame talks to the app ONLY through postMessage (validated
// by source), which we map to: post a turn / prefill the composer / open a link
// (the "changes & additions" interaction loop).

import { useAssistantRuntime } from "@assistant-ui/react";
import { useEffect, useMemo, useRef, useState } from "react";

const CSP =
	"<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; img-src data: https:; media-src data: https:; style-src 'unsafe-inline' https:; font-src https: data:; script-src 'unsafe-inline'; connect-src 'none'; form-action 'none'; base-uri 'none'\">";

// Transparent background + sensible defaults; legible on light & dark.
const BASE_STYLE =
	"<style>:root{color-scheme:light dark}html,body{margin:0}body{font-family:ui-sans-serif,system-ui,-apple-system,sans-serif;font-size:14px;line-height:1.5;color:#111;background:transparent;padding:2px}@media(prefers-color-scheme:dark){body{color:#eee}}*{box-sizing:border-box}</style>";

// Bridge: exposes window.aui.{send,compose,link} and auto-reports height. Posts
// to the parent with an __aui marker; the parent validates the source frame.
const BRIDGE = `<script>(function(){
function post(m){try{parent.postMessage(Object.assign({__aui:1},m),'*')}catch(e){}}
window.aui={send:function(p){post({type:'send',prompt:String(p==null?'':p)})},compose:function(p){post({type:'compose',prompt:String(p==null?'':p)})},link:function(h){post({type:'link',href:String(h==null?'':h)})}};
function h(){var b=document.body,e=document.documentElement;return Math.ceil(Math.max(b?b.scrollHeight:0,b?b.offsetHeight:0,e.scrollHeight,e.offsetHeight))}
function report(){post({type:'height',height:h()})}
window.addEventListener('load',function(){report();var im=document.images||[];for(var i=0;i<im.length;i++){if(!im[i].complete){im[i].addEventListener('load',report);im[i].addEventListener('error',report)}}});
try{var ro=new ResizeObserver(report);ro.observe(document.documentElement);if(document.body)ro.observe(document.body)}catch(e){}
setTimeout(report,50);setTimeout(report,200);setTimeout(report,600);
}())</script>`;

// Wrap the agent's body content into a full, sandboxed document. If it mistakenly
// returns a full doc, strip the outer shell so our CSP/bridge still apply.
function buildSrcDoc(html: string): string {
	let body = html ?? "";
	const m = body.match(/<body[^>]*>([\s\S]*?)<\/body>/i);
	if (m) body = m[1];
	else body = body.replace(/<\/?(?:!doctype|html|head|body)[^>]*>/gi, "");
	return `<!doctype html><html><head><meta charset="utf-8">${CSP}${BASE_STYLE}</head><body>${body}${BRIDGE}</body></html>`;
}

export function HtmlCanvas({ html }: { html: string }) {
	const runtime = useAssistantRuntime();
	const ref = useRef<HTMLIFrameElement>(null);
	const [height, setHeight] = useState(120);
	const srcDoc = useMemo(() => buildSrcDoc(html), [html]);

	useEffect(() => {
		function onMessage(e: MessageEvent) {
			// Only trust messages from THIS sandboxed frame (opaque origin → can't
			// check e.origin, so match the source window).
			if (!ref.current || e.source !== ref.current.contentWindow) return;
			const d = e.data as {
				__aui?: number;
				type?: string;
				height?: number;
				prompt?: string;
				href?: string;
			} | null;
			if (d?.__aui !== 1) return;
			if (d.type === "height" && typeof d.height === "number") {
				setHeight(Math.min(Math.max(d.height, 32), 4000));
			} else if (d.type === "send" && d.prompt) {
				runtime.thread.append({
					role: "user",
					content: [{ type: "text", text: String(d.prompt) }],
				});
			} else if (d.type === "compose" && d.prompt) {
				runtime.thread.composer.setText(String(d.prompt));
			} else if (d.type === "link" && d.href) {
				const u = String(d.href);
				if (/^https?:\/\//i.test(u))
					window.open(u, "_blank", "noopener,noreferrer");
			}
		}
		window.addEventListener("message", onMessage);
		return () => window.removeEventListener("message", onMessage);
	}, [runtime]);

	return (
		<iframe
			ref={ref}
			title="Generated UI"
			sandbox="allow-scripts"
			srcDoc={srcDoc}
			className="bg-muted/30 my-1 w-full rounded-lg border"
			// content-box so the reported content height IS the iframe viewport
			// height (border-box would subtract the 1px border → 2px overflow → scrollbar).
			style={{ height, boxSizing: "content-box" }}
		/>
	);
}
