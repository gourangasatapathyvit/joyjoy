"use client";

// Bespoke per-tool renderers for the agent's most visual built-in tools, wired
// into the `tool-call` switch in `thread.tsx` (the non-deprecated "inline tool
// render override" path — assistant-ui's `makeAssistantToolUI` is deprecated in
// favour of this). Each is a plain `ToolCallMessagePartComponent`, so they get
// the same props as the generic `ToolFallback` and reuse its collapsible shell +
// the shared `ToolApprovalControls`, meaning HITL gating is preserved verbatim.

import type {
	GenerativeUISpec,
	ToolCallMessagePartComponent,
	ToolCallMessagePartProps,
	ToolCallMessagePartStatus,
} from "@assistant-ui/react";
import { useMemo, useState } from "react";
import { computeLineDiff, diffStats } from "@/lib/diff";
import { cn } from "@/lib/utils";
import { GenerativeUI } from "./generative-ui";
import { HtmlCanvas } from "./html-canvas";
import { ToolApprovalControls, useToolNeedsAction } from "./tool-approval";
import {
	ToolFallbackContent,
	ToolFallbackError,
	ToolFallbackResult,
	ToolFallbackRoot,
	ToolFallbackTrigger,
} from "./tool-fallback";

/** Shared collapsible shell: identical chrome + approval + error/result handling
 * as the generic fallback, with a custom `body`. Keeps every tool UI consistent
 * and ensures none can accidentally drop the approval gate. */
function ToolShell({
	part,
	body,
	hideResult,
}: {
	part: ToolCallMessagePartProps;
	body: React.ReactNode;
	hideResult?: boolean;
}) {
	const needsAction = useToolNeedsAction(part.toolCallId, part.status?.type);
	const [open, setOpen] = useState(needsAction);
	const [prevNeedsAction, setPrevNeedsAction] = useState(needsAction);
	if (needsAction !== prevNeedsAction) {
		setPrevNeedsAction(needsAction);
		if (needsAction) setOpen(true);
	}

	const isCancelled =
		part.status?.type === "incomplete" && part.status.reason === "cancelled";

	return (
		<ToolFallbackRoot open={open} onOpenChange={setOpen}>
			<ToolFallbackTrigger toolName={part.toolName} status={part.status} />
			<ToolFallbackContent>
				<ToolFallbackError status={part.status} />
				<div className={cn("flex flex-col gap-2", isCancelled && "opacity-60")}>
					{body}
				</div>
				<ToolApprovalControls
					toolCallId={part.toolCallId}
					status={part.status}
					addResult={part.addResult}
					resume={part.resume}
					interrupt={part.interrupt}
					approval={part.approval}
					respondToApproval={part.respondToApproval}
				/>
				{!isCancelled && !hideResult && (
					<ToolFallbackResult result={part.result} />
				)}
			</ToolFallbackContent>
		</ToolFallbackRoot>
	);
}

function FilePathBadge({ path, note }: { path?: string; note?: string }) {
	if (!path) return null;
	return (
		<div className="flex flex-wrap items-center gap-2 text-xs">
			<code className="bg-muted rounded px-1.5 py-0.5 font-mono break-all">
				{path}
			</code>
			{note && <span className="text-muted-foreground">{note}</span>}
		</div>
	);
}

/** Best-effort extraction of human-readable stdout from a tool result that may
 * be a string or a structured object (stdout/output/result/text). */
function resultToText(result: unknown): string {
	if (result == null) return "";
	if (typeof result === "string") return result;
	if (typeof result === "object") {
		const o = result as Record<string, unknown>;
		const out = o.stdout ?? o.output ?? o.result ?? o.text;
		if (typeof out === "string") return out;
	}
	return JSON.stringify(result, null, 2);
}

function TerminalBlock({
	command,
	result,
	status,
}: {
	command?: string;
	result: unknown;
	status?: ToolCallMessagePartStatus;
}) {
	const text = resultToText(result);
	const isRunning = status?.type === "running";
	return (
		<div className="overflow-hidden rounded-md bg-zinc-950 font-mono text-xs text-zinc-100">
			{command && (
				<div className="border-b border-zinc-800 px-2.5 py-1.5 whitespace-pre-wrap">
					<span className="text-emerald-400 select-none">$ </span>
					{command}
				</div>
			)}
			{(text || isRunning) && (
				<pre className="max-h-80 overflow-auto px-2.5 py-1.5 whitespace-pre-wrap">
					{text || (isRunning ? "…" : "")}
				</pre>
			)}
		</div>
	);
}

function DiffView({ oldText, newText }: { oldText: string; newText: string }) {
	const rows = useMemo(
		() => computeLineDiff(oldText, newText),
		[oldText, newText],
	);
	const { added, removed } = useMemo(() => diffStats(rows), [rows]);

	if (rows.length === 0)
		return <p className="text-muted-foreground text-xs">No changes</p>;

	return (
		<div className="overflow-hidden rounded-md border text-xs">
			<div className="bg-muted/50 text-muted-foreground flex gap-3 px-2.5 py-1 font-medium tabular-nums">
				<span className="text-emerald-600 dark:text-emerald-400">+{added}</span>
				<span className="text-red-600 dark:text-red-400">−{removed}</span>
			</div>
			<div className="max-h-96 overflow-auto font-mono leading-relaxed">
				{rows.map((r, idx) => (
					<div
						// biome-ignore lint/suspicious/noArrayIndexKey: diff rows are a static, non-reordering snapshot
						key={`${r.type}-${idx}-${r.text}`}
						className={cn(
							"px-2.5 whitespace-pre-wrap",
							r.type === "add" &&
								"bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
							r.type === "del" &&
								"bg-red-500/10 text-red-700 dark:text-red-300",
							r.type === "ctx" && "text-muted-foreground",
						)}
					>
						<span className="select-none opacity-60">
							{r.type === "add" ? "+" : r.type === "del" ? "−" : " "}{" "}
						</span>
						{r.text || " "}
					</div>
				))}
			</div>
		</div>
	);
}

/** Parse deepagents' line-numbered read_file output (`"   12\t<text>"`, with
 * `12.1`-style continuation rows for wrapped long lines) into number + text.
 * Lines that don't match (e.g. the empty-file system reminder) keep no number. */
function parseNumberedLines(
	text: string,
): { no: string | null; text: string }[] {
	return text.split("\n").map((line) => {
		const m = line.match(/^\s*(\d+(?:\.\d+)?)\t(.*)$/);
		return m ? { no: m[1], text: m[2] } : { no: null, text: line };
	});
}

function CodeListing({ text }: { text: string }) {
	const lines = useMemo(() => parseNumberedLines(text), [text]);
	const hasNumbers = lines.some((l) => l.no !== null);
	return (
		<div className="bg-muted/30 max-h-96 overflow-auto rounded-md border font-mono text-xs">
			{lines.map((l, idx) => (
				// biome-ignore lint/suspicious/noArrayIndexKey: file listing is static, never reordered
				<div key={`${idx}-${l.no ?? ""}`} className="flex">
					{hasNumbers && (
						<span className="text-muted-foreground/60 border-border/60 shrink-0 select-none border-r px-2 text-right tabular-nums">
							{l.no ?? ""}
						</span>
					)}
					<span className="px-2.5 whitespace-pre-wrap">{l.text || " "}</span>
				</div>
			))}
		</div>
	);
}

const ReadFileToolUI: ToolCallMessagePartComponent = (part) => {
	const args = part.args as
		| { file_path?: string; offset?: number; limit?: number }
		| undefined;
	const range =
		args?.offset != null || args?.limit != null
			? `from line ${args?.offset ?? 0}${args?.limit != null ? `, ${args.limit} lines` : ""}`
			: undefined;
	// read_file of an image/PDF returns multimodal blocks (non-string) — fall back
	// to the generic result renderer for those.
	const text = typeof part.result === "string" ? part.result : "";
	return (
		<ToolShell
			part={part}
			hideResult={!!text}
			body={
				<>
					<FilePathBadge path={args?.file_path} note={range} />
					{text && <CodeListing text={text} />}
				</>
			}
		/>
	);
};

const ExecuteToolUI: ToolCallMessagePartComponent = (part) => {
	const args = part.args as { command?: string } | undefined;
	return (
		<ToolShell
			part={part}
			hideResult
			body={
				<TerminalBlock
					command={args?.command}
					result={part.result}
					status={part.status}
				/>
			}
		/>
	);
};

const WriteFileToolUI: ToolCallMessagePartComponent = (part) => {
	const args = part.args as
		| { file_path?: string; content?: string }
		| undefined;
	return (
		<ToolShell
			part={part}
			body={
				<>
					<FilePathBadge path={args?.file_path} note="new content" />
					<DiffView oldText="" newText={args?.content ?? ""} />
				</>
			}
		/>
	);
};

const EditFileToolUI: ToolCallMessagePartComponent = (part) => {
	const args = part.args as
		| {
				file_path?: string;
				old_string?: string;
				new_string?: string;
				replace_all?: boolean;
		  }
		| undefined;
	return (
		<ToolShell
			part={part}
			body={
				<>
					<FilePathBadge
						path={args?.file_path}
						note={args?.replace_all ? "replace all" : undefined}
					/>
					<DiffView
						oldText={args?.old_string ?? ""}
						newText={args?.new_string ?? ""}
					/>
				</>
			}
		/>
	);
};

/** Parse a Python list-repr string (`"['/a', '/b']"`, as `ls`/`glob` return via
 * `str(paths)`) into its items. Returns null when the text isn't a list repr
 * (e.g. an error string) so the caller can fall back to the raw renderer. */
function parsePyList(text: string): string[] | null {
	if (!text.trim().startsWith("[")) return null;
	const items: string[] = [];
	const re = /'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)"/g;
	let m: RegExpExecArray | null = re.exec(text);
	while (m !== null) {
		items.push((m[1] ?? m[2] ?? "").replace(/\\(['"\\])/g, "$1"));
		m = re.exec(text);
	}
	return items;
}

/** Split into lines, dropping trailing blank lines. */
function toLineArray(text: string): string[] {
	const lines = text.split("\n");
	while (lines.length && lines[lines.length - 1].trim() === "") lines.pop();
	return lines;
}

function MonoList({ lines, empty }: { lines: string[]; empty: string }) {
	if (lines.length === 0)
		return <p className="text-muted-foreground text-xs">{empty}</p>;
	return (
		<div className="bg-muted/30 max-h-96 overflow-auto rounded-md border px-2.5 py-1 font-mono text-xs">
			{lines.map((l, idx) => (
				// biome-ignore lint/suspicious/noArrayIndexKey: result lines are static, never reordered
				<div key={`${idx}-${l}`} className="whitespace-pre-wrap">
					{l || " "}
				</div>
			))}
		</div>
	);
}

function SearchHeader({ pattern, note }: { pattern?: string; note?: string }) {
	return (
		<div className="flex flex-wrap items-center gap-2 text-xs">
			{pattern != null && (
				<code className="bg-muted rounded px-1.5 py-0.5 font-mono break-all">
					{pattern}
				</code>
			)}
			{note && <span className="text-muted-foreground">{note}</span>}
		</div>
	);
}

const LsToolUI: ToolCallMessagePartComponent = (part) => {
	const args = part.args as { path?: string } | undefined;
	const entries = parsePyList(resultToText(part.result));
	return (
		<ToolShell
			part={part}
			hideResult={entries !== null}
			body={
				<>
					<FilePathBadge
						path={args?.path}
						note={
							entries
								? `${entries.length} ${entries.length === 1 ? "entry" : "entries"}`
								: undefined
						}
					/>
					{entries !== null && (
						<MonoList lines={entries} empty="Empty directory" />
					)}
				</>
			}
		/>
	);
};

const GlobToolUI: ToolCallMessagePartComponent = (part) => {
	const args = part.args as { pattern?: string; path?: string } | undefined;
	const entries = parsePyList(resultToText(part.result));
	const note = [
		args?.path,
		entries
			? `${entries.length} match${entries.length === 1 ? "" : "es"}`
			: null,
	]
		.filter(Boolean)
		.join(" · ");
	return (
		<ToolShell
			part={part}
			hideResult={entries !== null}
			body={
				<>
					<SearchHeader pattern={args?.pattern} note={note} />
					{entries !== null && <MonoList lines={entries} empty="No matches" />}
				</>
			}
		/>
	);
};

const GrepToolUI: ToolCallMessagePartComponent = (part) => {
	const args = part.args as
		| { pattern?: string; path?: string; glob?: string; output_mode?: string }
		| undefined;
	const isStr = typeof part.result === "string";
	const text = resultToText(part.result);
	const noMatches = text.trim() === "No matches found";
	const note = [
		args?.output_mode ?? "files_with_matches",
		args?.glob ? `glob ${args.glob}` : null,
		args?.path,
	]
		.filter(Boolean)
		.join(" · ");
	return (
		<ToolShell
			part={part}
			hideResult={isStr}
			body={
				<>
					<SearchHeader pattern={args?.pattern} note={note} />
					{isStr && (
						<MonoList
							lines={noMatches ? [] : toLineArray(text)}
							empty="No matches found"
						/>
					)}
				</>
			}
		/>
	);
};

const TodoChecklistUI: ToolCallMessagePartComponent = (part) => {
	const todos =
		(
			part.args as
				| { todos?: { content?: string; status?: string }[] }
				| undefined
		)?.todos ?? [];
	return (
		<ToolShell
			part={part}
			hideResult
			body={
				todos.length === 0 ? (
					<p className="text-muted-foreground text-xs">No todos</p>
				) : (
					<ul className="flex flex-col gap-1 text-sm">
						{todos.map((todo, idx) => {
							const status = todo.status ?? "pending";
							return (
								<li
									// biome-ignore lint/suspicious/noArrayIndexKey: ordered task list, position is the identity
									key={`${idx}-${todo.content}`}
									className="flex items-start gap-2"
								>
									<span
										className={cn(
											"mt-0.5 select-none",
											status === "completed" &&
												"text-emerald-600 dark:text-emerald-400",
											status === "in_progress" &&
												"text-amber-600 dark:text-amber-400",
											status === "pending" && "text-muted-foreground",
										)}
									>
										{status === "completed"
											? "✓"
											: status === "in_progress"
												? "◐"
												: "○"}
									</span>
									<span
										className={cn(
											status === "completed" &&
												"text-muted-foreground line-through",
										)}
									>
										{todo.content}
									</span>
								</li>
							);
						})}
					</ul>
				)
			}
		/>
	);
};

const SubagentToolUI: ToolCallMessagePartComponent = (part) => {
	const args = part.args as
		| { description?: string; subagent_type?: string }
		| undefined;
	const result = typeof part.result === "string" ? part.result : "";
	return (
		<ToolShell
			part={part}
			hideResult={!!result}
			body={
				<>
					{args?.subagent_type && (
						<div className="flex flex-wrap items-center gap-2 text-xs">
							<code className="bg-muted rounded px-1.5 py-0.5 font-mono">
								🤖 {args.subagent_type}
							</code>
						</div>
					)}
					{args?.description && (
						<p className="text-muted-foreground text-xs whitespace-pre-wrap">
							{args.description}
						</p>
					)}
					{result && (
						<div className="bg-muted/30 max-h-96 overflow-auto rounded-md border px-2.5 py-1.5 text-sm whitespace-pre-wrap">
							{result}
						</div>
					)}
				</>
			}
		/>
	);
};

const FetchContentToolUI: ToolCallMessagePartComponent = (part) => {
	const args = part.args as Record<string, unknown> | undefined;
	const url =
		(typeof args?.url === "string" && args.url) ||
		(typeof args?.uri === "string" && args.uri) ||
		(args
			? (Object.values(args).find(
					(v) => typeof v === "string" && /^https?:\/\//.test(v),
				) as string | undefined)
			: undefined);
	const text = resultToText(part.result);
	return (
		<ToolShell
			part={part}
			hideResult={!!text}
			body={
				<>
					{url && (
						<a
							href={url}
							target="_blank"
							rel="noopener noreferrer"
							className="text-primary text-xs break-all underline"
						>
							{url}
						</a>
					)}
					{text && (
						<div className="bg-muted/30 max-h-96 overflow-auto rounded-md border px-2.5 py-1.5 text-sm whitespace-pre-wrap">
							{text}
						</div>
					)}
				</>
			}
		/>
	);
};

/** Tool-name → bespoke renderer. `thread.tsx` consults this in the `tool-call`
 * switch, falling back to the generic `ToolFallback` for anything not listed.
 * (The generic fallback itself now renders structured JSON results as tables,
 * so unlisted MCP tools already display readably.) */
// render_ui: agent-emitted generative UI. Renders the spec inline at the tool's
// position in the turn (no tool-card chrome) — the rendered UI IS the output. The
// spec lives in the tool-call args, so it persists across reloads with history.
function RenderUiToolUI(part: ToolCallMessagePartProps) {
	const spec = (part.args as { spec?: GenerativeUISpec } | undefined)?.spec;
	if (!spec || typeof spec !== "object") return null;
	return <GenerativeUI spec={spec} />;
}

// render_html: the agent's HTML/CSS/JS rendered in a sandboxed iframe canvas.
function RenderHtmlToolUI(part: ToolCallMessagePartProps) {
	const html = (part.args as { html?: string } | undefined)?.html;
	if (typeof html !== "string" || !html.trim()) return null;
	return <HtmlCanvas html={html} />;
}

export const TOOL_UIS: Record<string, ToolCallMessagePartComponent> = {
	render_ui: RenderUiToolUI,
	render_html: RenderHtmlToolUI,
	write_todos: TodoChecklistUI,
	task: SubagentToolUI,
	fetch_content: FetchContentToolUI,
	execute: ExecuteToolUI,
	write_file: WriteFileToolUI,
	edit_file: EditFileToolUI,
	read_file: ReadFileToolUI,
	ls: LsToolUI,
	glob: GlobToolUI,
	grep: GrepToolUI,
};
