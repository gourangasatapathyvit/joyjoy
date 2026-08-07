// Converts joyjoy's `render_ui` wire format (a nested tree the model authors,
// unchanged across this refactor — see backend/app/agent/prompts.py) into
// json-render's flat `Spec` shape. The one real structural transform: a
// `Button` node's `props.action` (authored by the model exactly as today,
// nested inside props) is lifted out into a sibling `on.press` action binding,
// matching json-render's own convention — `nestedToFlat` itself only renames
// `component`→`type` and assigns keys, it has no notion of our `action` prop.

import type { GenerativeUINode, GenerativeUISpec } from "@assistant-ui/react";
import { nestedToFlat, type Spec } from "@json-render/core";

type ButtonAction = { type?: string; prompt?: string; href?: string };

function mapButtonAction(
	action: ButtonAction,
): { action: string; params: Record<string, unknown> } | undefined {
	if (action.type === "send")
		return { action: "sendPrompt", params: { prompt: action.prompt } };
	if (action.type === "compose")
		return { action: "composePrompt", params: { prompt: action.prompt } };
	if (action.type === "link")
		return { action: "openLink", params: { href: action.href } };
	return undefined;
}

function toNestedNode(node: GenerativeUINode): Record<string, unknown> {
	if (typeof node !== "object" || node === null) {
		// A string leaf (or any other malformed node) becomes an internal
		// text component — matching the tool-uis "malformed node → skipped"
		// behavior isn't possible here (nestedToFlat needs SOME node), so a
		// non-string/non-object node renders as empty text rather than crashing.
		return {
			type: "__Text",
			props: { value: typeof node === "string" ? node : "" },
			children: [],
		};
	}
	const { component, props = {}, children = [] } = node;
	const nestedChildren = children.map(toNestedNode);
	if (
		component === "Button" &&
		props.action &&
		typeof props.action === "object"
	) {
		const { action, ...restProps } = props as Record<string, unknown>;
		const onPress = mapButtonAction(action as ButtonAction);
		return {
			type: component,
			props: restProps,
			children: nestedChildren,
			...(onPress ? { on: { press: onPress } } : {}),
		};
	}
	return { type: component, props, children: nestedChildren };
}

/** Convert joyjoy's persisted `render_ui` spec into json-render's flat `Spec`. */
export function joyjoySpecToFlatSpec(spec: GenerativeUISpec): Spec {
	const roots = Array.isArray(spec.root)
		? spec.root
		: spec.root
			? [spec.root]
			: [];
	const nested =
		roots.length === 1
			? toNestedNode(roots[0])
			: { type: "__Fragment", props: {}, children: roots.map(toNestedNode) };
	return nestedToFlat(nested);
}
