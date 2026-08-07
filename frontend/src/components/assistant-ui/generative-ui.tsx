"use client";

// Generative UI — renders an agent-emitted JSON component tree (the `render_ui`
// tool's spec) via json-render's catalog/registry engine (see
// generative-ui-catalog.ts / generative-ui-registry.tsx for the 22 ported
// components, render-ui-spec.ts for the nested→flat wire-format bridge). The
// wire format (persisted in the tool-call args, unchanged by this refactor)
// still arrives as a nested tree from the run SSE stream / reload history.
//
// SECURITY: the registry gates WHICH components render; props are agent-supplied
// (untrusted). Components read only specific, typed props (never blind-spread
// onto the DOM), urls are sanitized, and dangerouslySetInnerHTML is never used.

import type { GenerativeUISpec } from "@assistant-ui/react";
import { useAssistantRuntime } from "@assistant-ui/react";
import type { ActionHandler } from "@json-render/core";
import {
	ActionProvider,
	type ComponentRenderer,
	Renderer,
	StateProvider,
	VisibilityProvider,
} from "@json-render/react";
import { useMemo } from "react";
import { joyjoySpecToFlatSpec } from "@/lib/render-ui-spec";
import { catalog } from "./generative-ui-catalog";
import { registry } from "./generative-ui-registry";

// Block javascript:/data:/vbscript: and other non-http(s)/mailto schemes —
// mirrors the same check `generative-ui-registry.tsx`'s components use.
function safeUrl(v: unknown): string | undefined {
	const s = typeof v === "string" ? v.trim() : "";
	if (!s) return undefined;
	if (/^(https?:|mailto:|\/|#|\.)/i.test(s)) return s;
	return undefined;
}

/** Names the agent can use, exported for the tool description / prompt. */
export const GENERATIVE_UI_COMPONENTS = catalog.componentNames.filter(
	(name) => !name.startsWith("__"),
);

function Fallback({ element }: { element: { type: string } }) {
	return (
		<span className="text-muted-foreground rounded border border-dashed px-1.5 py-0.5 text-xs">
			Unsupported UI component: {element.type}
		</span>
	);
}
const fallback = Fallback as unknown as ComponentRenderer;

/** The 3 Button actions — same underlying behavior as before the json-render
 * refactor, just invoked as registered action handlers (via the `on.press`
 * binding `render-ui-spec.ts` synthesizes from `props.action`) instead of an
 * inline onClick calling `useAssistantRuntime()` directly. */
function useJoyjoyActionHandlers(): Record<string, ActionHandler> {
	const runtime = useAssistantRuntime();
	return useMemo(
		() => ({
			sendPrompt: (params: { prompt?: string }) => {
				if (params.prompt) {
					runtime.thread.append({
						role: "user",
						content: [{ type: "text", text: params.prompt }],
					});
				}
			},
			composePrompt: (params: { prompt?: string }) => {
				if (params.prompt) runtime.thread.composer.setText(params.prompt);
			},
			openLink: (params: { href?: string }) => {
				const u = safeUrl(params.href);
				if (u) window.open(u, "_blank", "noopener,noreferrer");
			},
		}),
		[runtime],
	);
}

/** Render a generative-ui spec via json-render's `<Renderer>`, resolving
 * component names against our registry (the security boundary; unknown names
 * hit Fallback). */
export function GenerativeUI({ spec }: { spec: GenerativeUISpec }) {
	const actionHandlers = useJoyjoyActionHandlers();
	if (!spec?.root) return null;
	const flat = joyjoySpecToFlatSpec(spec);
	return (
		<div className="my-1 flex flex-col gap-2">
			<StateProvider initialState={flat.state ?? {}}>
				<VisibilityProvider>
					<ActionProvider handlers={actionHandlers}>
						<Renderer spec={flat} registry={registry} fallback={fallback} />
					</ActionProvider>
				</VisibilityProvider>
			</StateProvider>
		</div>
	);
}
