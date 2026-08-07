// Catalog for the `render_ui` tool's component vocabulary — the single typed
// source of truth for each of the 22 components' props (previously only
// implicit in each component's defensive `str`/`optStr`/`numOf`/`arr` reads).
// Not used for runtime validation (we never call `catalog.validate()` — the
// wire format/vocabulary is owned by backend/app/agent/prompts.py and must
// stay byte-for-byte compatible with already-persisted chat history), only for
// typing `generative-ui-registry.tsx`'s component functions and as living
// documentation. Schemas are intentionally loose to match what the renderer
// already tolerates, not tightened into something a real spec could fail.
import { defineCatalog } from "@json-render/core";
import { schema } from "@json-render/react/schema";
import { z } from "zod";

const keyValueItem = z.object({
	key: z.unknown().optional(),
	value: z.unknown().optional(),
});

export const catalog = defineCatalog(schema, {
	components: {
		// ── layout ──────────────────────────────────────────────────────────
		Stack: {
			props: z.object({ direction: z.string().optional() }),
			slots: ["default"],
			description: "Flex layout container",
		},
		Grid: {
			props: z.object({ columns: z.number().optional() }),
			slots: ["default"],
			description: "CSS grid layout (1-4 columns)",
		},
		Card: {
			props: z.object({
				title: z.string().optional(),
				description: z.string().optional(),
			}),
			slots: ["default"],
			description: "Titled container card",
		},
		Divider: { props: z.object({}), slots: [], description: "Horizontal rule" },
		Spacer: {
			props: z.object({ size: z.number().optional() }),
			slots: [],
			description: "Fixed-height blank space",
		},

		// ── content ─────────────────────────────────────────────────────────
		Heading: {
			props: z.object({
				text: z.string().optional(),
				level: z.number().optional(),
			}),
			slots: [],
			description: "Section heading, level 1-4",
		},
		Text: {
			props: z.object({
				text: z.string().optional(),
				muted: z.boolean().optional(),
			}),
			slots: [],
			description: "Body text",
		},
		Badge: {
			props: z.object({
				text: z.string().optional(),
				variant: z.string().optional(),
			}),
			slots: [],
			description: "Small status pill",
		},
		KeyValue: {
			props: z.object({
				items: z.array(keyValueItem).optional(),
				pairs: z.array(keyValueItem).optional(),
			}),
			slots: [],
			description: "Key/value detail list",
		},
		Stat: {
			props: z.object({
				label: z.string().optional(),
				value: z.union([z.string(), z.number()]).optional(),
				delta: z.union([z.string(), z.number()]).optional(),
				deltaDirection: z.enum(["up", "down"]).optional(),
			}),
			slots: [],
			description: "Single metric with optional delta indicator",
		},
		Table: {
			props: z.object({
				columns: z.array(z.unknown()).optional(),
				rows: z.array(z.array(z.unknown())).optional(),
			}),
			slots: [],
			description: "Simple data table",
		},
		List: {
			props: z.object({
				items: z.array(z.unknown()).optional(),
				ordered: z.boolean().optional(),
			}),
			slots: [],
			description: "Bulleted or numbered list",
		},
		Image: {
			props: z.object({
				src: z.string().optional(),
				alt: z.string().optional(),
				width: z.number().optional(),
			}),
			slots: [],
			description: "Image (supports workspace: URLs)",
		},
		Link: {
			props: z.object({
				href: z.string().optional(),
				text: z.string().optional(),
			}),
			slots: [],
			description: "Hyperlink (supports workspace: URLs)",
		},
		Progress: {
			props: z.object({
				value: z.number().optional(),
				label: z.string().optional(),
			}),
			slots: [],
			description: "Progress bar, 0-100",
		},
		Alert: {
			props: z.object({
				variant: z.string().optional(),
				title: z.string().optional(),
				text: z.string().optional(),
			}),
			slots: ["default"],
			description: "Callout banner (info/success/warning/error)",
		},
		Code: {
			props: z.object({
				code: z.string().optional(),
				language: z.string().optional(),
			}),
			slots: [],
			description: "Preformatted code block",
		},
		Chart: {
			props: z.object({
				type: z.string().optional(),
				data: z.array(z.unknown()).optional(),
				labels: z.array(z.unknown()).optional(),
			}),
			slots: [],
			description: "Bar/line/sparkline chart",
		},
		Avatar: {
			props: z.object({
				name: z.string().optional(),
				src: z.string().optional(),
				size: z.number().optional(),
			}),
			slots: [],
			description: "Avatar with initials fallback",
		},

		// ── interactive ─────────────────────────────────────────────────────
		Button: {
			props: z.object({
				label: z.string().optional(),
				variant: z.string().optional(),
				action: z
					.object({
						type: z.string().optional(),
						prompt: z.string().optional(),
						href: z.string().optional(),
					})
					.optional(),
			}),
			slots: [],
			description: "Clickable button; action describes the click behavior",
		},
		Tabs: {
			props: z.object({ labels: z.array(z.unknown()).optional() }),
			slots: ["default"],
			description: "Tabbed panels; children map 1:1 to labels by position",
		},
		Accordion: {
			props: z.object({ labels: z.array(z.unknown()).optional() }),
			slots: ["default"],
			description: "Collapsible panels; children map 1:1 to labels by position",
		},

		// ── internal-only plumbing (never in the model-facing vocabulary) ───
		__Text: {
			props: z.object({ value: z.string().optional() }),
			slots: [],
			description: "internal: raw string leaf node",
		},
		__Fragment: {
			props: z.object({}),
			slots: ["default"],
			description: "internal: wrapper for a multi-root spec.root array",
		},
	},
	actions: {},
});
