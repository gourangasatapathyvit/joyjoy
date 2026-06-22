import {
	ComposerPrimitive,
	type Unstable_DirectiveFormatter,
	type Unstable_DirectiveSegment,
	unstable_useMentionAdapter,
	unstable_useSlashCommandAdapter,
	useComposerRuntime,
} from "@assistant-ui/react";
import type { FC } from "react";
import { useMcpTools, useSkills } from "@/api/queries";

// ChatGPT/Claude-style composer triggers, built on assistant-ui's (unstable)
// TriggerPopover primitives:
//   "/"  → slash commands = enabled skills; selecting one nudges the agent to
//          use that skill (skills auto-load, so this is a discoverability hint).
//   "@"  → mentions = available MCP tools; selecting one inserts a plain
//          "@toolname" reference that travels with the message text.
//
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

const POPOVER_CLS =
	"aui-trigger-popover bg-popover text-popover-foreground border-border absolute bottom-full left-0 z-50 mb-2 flex max-h-72 w-[min(24rem,90vw)] flex-col gap-0.5 overflow-y-auto rounded-xl border p-1.5 shadow-lg";
const ITEM_CLS =
	"aui-trigger-item flex w-full cursor-pointer flex-col items-start gap-0.5 rounded-lg px-2.5 py-1.5 text-left text-sm outline-none data-[highlighted=true]:bg-accent data-[highlighted=true]:text-accent-foreground";

const TriggerItems: FC<{ empty: string }> = ({ empty }) => (
	<ComposerPrimitive.Unstable_TriggerPopoverItems>
		{(items) =>
			items.length === 0 ? (
				<div className="text-muted-foreground px-2.5 py-1.5 text-sm">
					{empty}
				</div>
			) : (
				items.map((item, i) => (
					<ComposerPrimitive.Unstable_TriggerPopoverItem
						key={item.id}
						item={item}
						index={i}
						className={ITEM_CLS}
					>
						<span className="font-medium">{item.label}</span>
						{item.description ? (
							<span className="text-muted-foreground line-clamp-1 text-xs">
								{item.description}
							</span>
						) : null}
					</ComposerPrimitive.Unstable_TriggerPopoverItem>
				))
			)
		}
	</ComposerPrimitive.Unstable_TriggerPopoverItems>
);

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
		items: (tools.data?.tools ?? []).map((tool) => ({
			id: `${tool.server}:${tool.name}`,
			type: "tool",
			label: tool.name,
			description: tool.description,
		})),
	});

	return (
		<>
			<ComposerPrimitive.Unstable_TriggerPopover
				char="/"
				adapter={slash.adapter}
				className={POPOVER_CLS}
			>
				<ComposerPrimitive.Unstable_TriggerPopover.Action {...slash.action} />
				<TriggerItems empty="No skills available" />
			</ComposerPrimitive.Unstable_TriggerPopover>

			<ComposerPrimitive.Unstable_TriggerPopover
				char="@"
				adapter={mention.adapter}
				className={POPOVER_CLS}
			>
				<ComposerPrimitive.Unstable_TriggerPopover.Directive
					{...mention.directive}
				/>
				<TriggerItems empty="No tools available" />
			</ComposerPrimitive.Unstable_TriggerPopover>
		</>
	);
};
