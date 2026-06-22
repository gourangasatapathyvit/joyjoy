import {
	type Unstable_DirectiveFormatter,
	type Unstable_DirectiveSegment,
	unstable_useMentionAdapter,
	unstable_useSlashCommandAdapter,
	useComposerRuntime,
} from "@assistant-ui/react";
import type { FC } from "react";
import { useMcpTools, useSkills } from "@/api/queries";
import { ComposerTriggerPopover } from "@/components/assistant-ui/composer-trigger-popover";

// ChatGPT/Claude-style composer triggers. The popover UI is assistant-ui's
// official registry component (`composer-trigger-popover`); we only supply the
// adapters + behavior:
//   "/"  → slash commands = enabled skills; selecting one nudges the agent to
//          use that skill (skills auto-load, so this is a discoverability hint).
//   "@"  → mentions = available MCP tools; selecting one inserts a plain
//          "@toolname" reference that travels with the message text.
// Both adapters are search-only (empty categories) so the popover shows the
// full list under the bare trigger char and filters as the user types.

// "/" uses an Action: it inserts a full sentence (no leading "/"), so the
// popover closes cleanly. Append after removeOnExecute has stripped the
// trigger token on the same tick.
const appendAfterTrigger = (
	runtime: ReturnType<typeof useComposerRuntime>,
	insert: string,
) => {
	if (!runtime) return;
	setTimeout(() => {
		const cur = runtime.getState().text;
		const prefix = cur ? `${cur.replace(/\s+$/, "")} ` : "";
		runtime.setText(`${prefix}${insert}`);
	}, 0);
};

// After a mention is inserted, the trigger resource leaves the tracked cursor
// at the trigger offset (it only advances it on close()), so detection keeps
// matching the just-inserted "@token" and the popover stays open on a plain
// <textarea>. Move the caret to the end and fire `select` so ComposerInput
// reports the new position → detection deactivates → popover closes.
const closeTriggerAfterInsert = () => {
	setTimeout(() => {
		const ta = document.querySelector<HTMLTextAreaElement>(
			"textarea.aui-composer-input",
		);
		if (!ta) return;
		ta.focus();
		const end = ta.value.length;
		ta.setSelectionRange(end, end);
		ta.dispatchEvent(new Event("select", { bubbles: true }));
	}, 0);
};

// "@" uses a Directive (the primitive owns cursor placement + popover close).
// We override the formatter so mentions serialize to a plain, agent-readable
// "@toolname" instead of assistant-ui's default `:tool[name]{…}` markup.
const MENTION_RE = /@([A-Za-z0-9_][A-Za-z0-9_\-.]*)/gu;
const mentionFormatter: Unstable_DirectiveFormatter = {
	serialize: (item) => `@${item.label}`,
	parse: (text) => {
		const segments: Unstable_DirectiveSegment[] = [];
		let last = 0;
		for (const m of text.matchAll(MENTION_RE)) {
			const idx = m.index ?? 0;
			if (idx > last)
				segments.push({ kind: "text", text: text.slice(last, idx) });
			segments.push({ kind: "mention", type: "tool", label: m[1], id: m[1] });
			last = idx + m[0].length;
		}
		if (last < text.length)
			segments.push({ kind: "text", text: text.slice(last) });
		return segments;
	},
};

export const ComposerTriggers: FC = () => {
	const composerRuntime = useComposerRuntime();
	const skills = useSkills();
	const tools = useMcpTools();

	const slash = unstable_useSlashCommandAdapter({
		removeOnExecute: true,
		commands: (skills.data?.skills ?? [])
			.filter((s) => s.enabled)
			.map((s) => ({
				id: s.name,
				label: s.name,
				description: s.description,
				execute: () =>
					appendAfterTrigger(composerRuntime, `Use the "${s.name}" skill. `),
			})),
	});

	const mention = unstable_useMentionAdapter({
		includeModelContextTools: false,
		formatter: mentionFormatter,
		onInserted: closeTriggerAfterInsert,
		items: (tools.data?.tools ?? []).map((tool) => ({
			id: `${tool.server}:${tool.name}`,
			type: "tool",
			label: tool.name,
			description: tool.description,
		})),
	});

	return (
		<>
			<ComposerTriggerPopover
				char="/"
				adapter={slash.adapter}
				action={slash.action}
				emptyItemsLabel="No skills available"
			/>
			<ComposerTriggerPopover
				char="@"
				adapter={mention.adapter}
				directive={mention.directive}
				emptyItemsLabel="No tools available"
			/>
		</>
	);
};
