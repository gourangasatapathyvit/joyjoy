"use client";

// Generative UI — renders an agent-emitted JSON component tree (the `render_ui`
// tool's spec) from a frontend allowlist. Inspired by assistant-ui's
// MessagePrimitive.GenerativeUI, adapted to our external-store thread: specs
// arrive over the run SSE stream and are rendered here.
//
// SECURITY: the allowlist gates WHICH components render; props are agent-supplied
// (untrusted). Components read only specific, typed props (never blind-spread
// onto the DOM), urls are sanitized, and dangerouslySetInnerHTML is never used.

import {
	type GenerativeUIComponentRegistry,
	type GenerativeUISpec,
	MessagePrimitive,
	useAssistantRuntime,
} from "@assistant-ui/react";
import {
	CircleAlertIcon,
	CircleCheckIcon,
	InfoIcon,
	TriangleAlertIcon,
} from "lucide-react";
import { type ReactNode, useState } from "react";
import { mediaUrl } from "@/lib/media";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/store/chat";

// ── prop readers (defensive: agent props are untrusted) ────────────────────
type Props = Record<string, unknown>;
const str = (v: unknown, d = ""): string => (typeof v === "string" ? v : d);
const optStr = (v: unknown): string | undefined =>
	typeof v === "string" ? v : undefined;
const numOf = (v: unknown): number | undefined =>
	typeof v === "number"
		? v
		: typeof v === "string" && v.trim() !== "" && !Number.isNaN(Number(v))
			? Number(v)
			: undefined;
const arr = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);

// Block javascript:/data:/vbscript: and other non-http(s)/mailto schemes.
function safeUrl(v: unknown): string | undefined {
	const s = optStr(v)?.trim();
	if (!s) return undefined;
	if (/^(https?:|mailto:|\/|#|\.)/i.test(s)) return s;
	return undefined;
}

// Resolve a `workspace:<path>` scheme to the active thread's media URL (so the
// agent can show files it created), otherwise sanitize as a normal URL.
function resolveUrl(v: unknown, threadId: string): string | undefined {
	const s = optStr(v)?.trim();
	if (!s) return undefined;
	if (s.startsWith("workspace:"))
		return mediaUrl(threadId, s.slice("workspace:".length));
	return safeUrl(s);
}

type GenComponent = (p: Props & { children?: ReactNode }) => ReactNode;

// ── layout ─────────────────────────────────────────────────────────────────
const Stack: GenComponent = ({ children, ...p }) => {
	const horizontal = str(p.direction) === "horizontal";
	return (
		<div
			className={cn(
				"flex",
				horizontal ? "flex-row flex-wrap items-center" : "flex-col",
				"gap-2",
			)}
		>
			{children}
		</div>
	);
};

const Grid: GenComponent = ({ children, ...p }) => {
	const cols = Math.min(Math.max(numOf(p.columns) ?? 2, 1), 4);
	const colsClass = {
		1: "grid-cols-1",
		2: "grid-cols-2",
		3: "grid-cols-3",
		4: "grid-cols-4",
	}[cols];
	return <div className={cn("grid gap-3", colsClass)}>{children}</div>;
};

const Card: GenComponent = ({ children, ...p }) => {
	const title = optStr(p.title);
	const description = optStr(p.description);
	return (
		<div className="bg-card text-card-foreground rounded-xl border p-4 shadow-sm">
			{title && <div className="text-sm font-semibold">{title}</div>}
			{description && (
				<div className="text-muted-foreground mt-0.5 text-xs">
					{description}
				</div>
			)}
			{children && <div className={cn(title && "mt-3")}>{children}</div>}
		</div>
	);
};

const Divider: GenComponent = () => <hr className="border-border my-1" />;
const Spacer: GenComponent = ({ ...p }) => (
	<div style={{ height: `${Math.min(numOf(p.size) ?? 8, 64)}px` }} />
);

// ── content ────────────────────────────────────────────────────────────────
const Heading: GenComponent = ({ ...p }) => {
	const level = Math.min(Math.max(numOf(p.level) ?? 2, 1), 4);
	const sz = { 1: "text-xl", 2: "text-lg", 3: "text-base", 4: "text-sm" }[
		level
	];
	return <div className={cn("font-semibold", sz)}>{str(p.text)}</div>;
};

const Text: GenComponent = ({ ...p }) => (
	<p
		className={cn(
			"text-sm leading-relaxed",
			p.muted ? "text-muted-foreground" : undefined,
		)}
	>
		{str(p.text)}
	</p>
);

const BADGE_VARIANTS: Record<string, string> = {
	default: "bg-muted text-foreground",
	primary: "bg-primary/15 text-primary",
	success: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
	warning: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
	error: "bg-red-500/15 text-red-600 dark:text-red-400",
	info: "bg-blue-500/15 text-blue-600 dark:text-blue-400",
};
const Badge: GenComponent = ({ ...p }) => (
	<span
		className={cn(
			"inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
			BADGE_VARIANTS[str(p.variant, "default")] ?? BADGE_VARIANTS.default,
		)}
	>
		{str(p.text)}
	</span>
);

const KeyValue: GenComponent = ({ ...p }) => {
	const items = arr<{ key?: unknown; value?: unknown }>(p.items ?? p.pairs);
	if (!items.length) return null;
	return (
		<dl className="grid gap-1 text-sm">
			{items.map((it, i) => (
				// biome-ignore lint/suspicious/noArrayIndexKey: positional data row
				<div key={i} className="flex items-baseline justify-between gap-4">
					<dt className="text-muted-foreground">{str(it.key)}</dt>
					<dd className="font-medium tabular-nums">{str(it.value)}</dd>
				</div>
			))}
		</dl>
	);
};

const Stat: GenComponent = ({ ...p }) => {
	const delta = optStr(p.delta);
	const dir = str(p.deltaDirection); // up | down
	return (
		<div className="flex flex-col gap-0.5">
			<span className="text-muted-foreground text-xs">{str(p.label)}</span>
			<span className="text-2xl font-semibold tabular-nums">
				{str(p.value)}
			</span>
			{delta && (
				<span
					className={cn(
						"text-xs font-medium",
						dir === "up"
							? "text-emerald-500"
							: dir === "down"
								? "text-red-500"
								: "text-muted-foreground",
					)}
				>
					{dir === "up" ? "▲ " : dir === "down" ? "▼ " : ""}
					{delta}
				</span>
			)}
		</div>
	);
};

const Table: GenComponent = ({ ...p }) => {
	const columns = arr<unknown>(p.columns).map((c) => str(c));
	const rows = arr<unknown[]>(p.rows);
	if (!columns.length && !rows.length) return null;
	return (
		<div className="overflow-x-auto rounded-lg border">
			<table className="w-full text-sm">
				{columns.length > 0 && (
					<thead className="bg-muted/50 text-muted-foreground">
						<tr>
							{columns.map((c, i) => (
								// biome-ignore lint/suspicious/noArrayIndexKey: positional column
								<th key={i} className="px-3 py-1.5 text-left font-medium">
									{c}
								</th>
							))}
						</tr>
					</thead>
				)}
				<tbody>
					{rows.map((row, ri) => (
						// biome-ignore lint/suspicious/noArrayIndexKey: positional row
						<tr key={ri} className="border-t">
							{arr<unknown>(row).map((cell, ci) => (
								// biome-ignore lint/suspicious/noArrayIndexKey: positional cell
								<td key={ci} className="px-3 py-1.5">
									{str(cell)}
								</td>
							))}
						</tr>
					))}
				</tbody>
			</table>
		</div>
	);
};

const List: GenComponent = ({ ...p }) => {
	const items = arr<unknown>(p.items).map((x) => str(x));
	if (!items.length) return null;
	const Tag = p.ordered ? "ol" : "ul";
	return (
		<Tag
			className={cn(
				"ms-5 space-y-1 text-sm",
				p.ordered ? "list-decimal" : "list-disc",
			)}
		>
			{items.map((it, i) => (
				// biome-ignore lint/suspicious/noArrayIndexKey: positional list item
				<li key={i}>{it}</li>
			))}
		</Tag>
	);
};

const Image: GenComponent = ({ ...p }) => {
	const threadId = useChatStore((s) => s.threadId);
	const src = resolveUrl(p.src, threadId);
	if (!src) return null;
	const width = numOf(p.width);
	return (
		<img
			src={src}
			alt={str(p.alt)}
			className="max-w-full rounded-lg"
			style={width ? { width: `${Math.min(width, 800)}px` } : undefined}
		/>
	);
};

const Link: GenComponent = ({ ...p }) => {
	const threadId = useChatStore((s) => s.threadId);
	const href = resolveUrl(p.href, threadId);
	if (!href) return <span>{str(p.text)}</span>;
	return (
		<a
			href={href}
			target="_blank"
			rel="noopener noreferrer"
			className="text-primary hover:underline"
		>
			{str(p.text, href)}
		</a>
	);
};

const Progress: GenComponent = ({ ...p }) => {
	const value = Math.min(Math.max(numOf(p.value) ?? 0, 0), 100);
	return (
		<div className="flex flex-col gap-1">
			<div className="flex items-center justify-between text-xs">
				<span className="text-muted-foreground">{str(p.label)}</span>
				<span className="tabular-nums">{Math.round(value)}%</span>
			</div>
			<div className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
				<div
					className="bg-primary h-full rounded-full"
					style={{ width: `${value}%` }}
				/>
			</div>
		</div>
	);
};

const ALERT_VARIANTS: Record<string, { cls: string; Icon: typeof InfoIcon }> = {
	info: {
		cls: "border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-300",
		Icon: InfoIcon,
	},
	success: {
		cls: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
		Icon: CircleCheckIcon,
	},
	warning: {
		cls: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
		Icon: TriangleAlertIcon,
	},
	error: {
		cls: "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300",
		Icon: CircleAlertIcon,
	},
};
const Alert: GenComponent = ({ children, ...p }) => {
	const v = ALERT_VARIANTS[str(p.variant, "info")] ?? ALERT_VARIANTS.info;
	const Icon = v.Icon;
	return (
		<div className={cn("flex gap-2 rounded-lg border p-3 text-sm", v.cls)}>
			<Icon className="mt-0.5 size-4 shrink-0" />
			<div className="flex flex-col gap-0.5">
				{optStr(p.title) && <div className="font-medium">{str(p.title)}</div>}
				{optStr(p.text) && <div>{str(p.text)}</div>}
				{children}
			</div>
		</div>
	);
};

const Code: GenComponent = ({ ...p }) => (
	<pre className="bg-muted overflow-x-auto rounded-lg p-3 text-xs">
		<code>{str(p.code)}</code>
	</pre>
);

const Chart: GenComponent = ({ ...p }) => {
	const data = arr<unknown>(p.data).map((d) => numOf(d) ?? 0);
	if (!data.length) return null;
	const labels = arr<unknown>(p.labels).map((l) => str(l));
	const max = Math.max(...data, 1);
	const type = str(p.type, "bar");
	if (type === "line" || type === "sparkline") {
		const W = 200;
		const H = 48;
		const min = Math.min(...data, 0);
		const span = max - min || 1;
		const denom = data.length - 1 || 1;
		const pts = data
			.map((v, i) => `${(i / denom) * W},${H - ((v - min) / span) * H}`)
			.join(" ");
		return (
			<svg
				viewBox={`0 0 ${W} ${H}`}
				className="text-primary h-12 w-full"
				preserveAspectRatio="none"
				fill="none"
				aria-hidden="true"
			>
				<polyline
					points={pts}
					stroke="currentColor"
					strokeWidth={2}
					strokeLinejoin="round"
					strokeLinecap="round"
				/>
			</svg>
		);
	}
	return (
		<div className="flex h-24 items-end gap-1">
			{data.map((v, i) => (
				// biome-ignore lint/suspicious/noArrayIndexKey: positional bar
				<div key={i} className="flex flex-1 flex-col items-center gap-1">
					<div
						className="bg-primary w-full rounded-t"
						style={{ height: `${Math.max((v / max) * 100, 1)}%` }}
						title={String(v)}
					/>
					{labels[i] && (
						<span className="text-muted-foreground w-full truncate text-center text-[10px]">
							{labels[i]}
						</span>
					)}
				</div>
			))}
		</div>
	);
};

const Accordion: GenComponent = ({ children, ...p }) => {
	const labels = arr<unknown>(p.labels).map((l) => str(l));
	const panels = Array.isArray(children) ? children : [children];
	if (!labels.length) return <>{children}</>;
	return (
		<div className="divide-y rounded-lg border">
			{labels.map((l, i) => (
				<details key={l} className="group">
					<summary className="cursor-pointer list-none px-3 py-2 text-sm font-medium [&::-webkit-details-marker]:hidden">
						{l}
					</summary>
					<div className="px-3 pb-3 text-sm">{panels[i] ?? null}</div>
				</details>
			))}
		</div>
	);
};

const Avatar: GenComponent = ({ ...p }) => {
	const src = safeUrl(p.src);
	const name = str(p.name);
	const initials =
		name
			.split(/\s+/)
			.map((w) => w[0])
			.filter(Boolean)
			.slice(0, 2)
			.join("")
			.toUpperCase() || "?";
	const size = Math.min(Math.max(numOf(p.size) ?? 40, 20), 96);
	return (
		<span
			className="bg-muted text-muted-foreground inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full text-xs font-medium"
			style={{ width: size, height: size }}
		>
			{src ? (
				<img src={src} alt={name} className="h-full w-full object-cover" />
			) : (
				initials
			)}
		</span>
	);
};

// ── interactive ──────────────────────────────────────────────────────────────
const BUTTON_VARIANTS: Record<string, string> = {
	primary: "bg-primary text-primary-foreground hover:bg-primary/90",
	default: "border bg-transparent hover:bg-accent hover:text-accent-foreground",
	ghost: "hover:bg-accent hover:text-accent-foreground",
};
const Button: GenComponent = ({ ...p }) => {
	const runtime = useAssistantRuntime();
	const label = str(p.label, "Button");
	const action = (p.action ?? {}) as {
		type?: string;
		prompt?: string;
		href?: string;
	};
	const onClick = () => {
		if (action.type === "send" && optStr(action.prompt)) {
			// Post the prompt as the user's next turn.
			runtime.thread.append({
				role: "user",
				content: [{ type: "text", text: String(action.prompt) }],
			});
		} else if (action.type === "compose" && optStr(action.prompt)) {
			// Prefill the thread composer without sending — user can edit, then send.
			runtime.thread.composer.setText(String(action.prompt));
		} else if (action.type === "link") {
			const u = safeUrl(action.href);
			if (u) window.open(u, "_blank", "noopener,noreferrer");
		}
	};
	return (
		<button
			type="button"
			onClick={onClick}
			className={cn(
				"focus-visible:ring-ring/50 inline-flex w-fit items-center justify-center rounded-md px-3 py-1.5 text-sm font-medium transition-colors outline-none focus-visible:ring-2",
				BUTTON_VARIANTS[str(p.variant, "default")] ?? BUTTON_VARIANTS.default,
			)}
		>
			{label}
		</button>
	);
};

const Tabs: GenComponent = ({ children, ...p }) => {
	const labels = arr<unknown>(p.labels).map((l) => str(l));
	const panels = Array.isArray(children) ? children : [children];
	const [active, setActive] = useState(0);
	if (!labels.length) return <>{children}</>;
	return (
		<div className="flex flex-col gap-2">
			<div className="flex gap-1 border-b">
				{labels.map((l, i) => (
					<button
						key={l}
						type="button"
						onClick={() => setActive(i)}
						className={cn(
							"-mb-px border-b-2 px-3 py-1.5 text-sm transition-colors",
							i === active
								? "border-primary text-foreground font-medium"
								: "text-muted-foreground hover:text-foreground border-transparent",
						)}
					>
						{l}
					</button>
				))}
			</div>
			<div>{panels[active] ?? null}</div>
		</div>
	);
};

// ── allowlist (the security boundary — names not here are rejected) ──────────
const ALLOWLIST: GenerativeUIComponentRegistry = {
	Stack,
	Grid,
	Card,
	Divider,
	Spacer,
	Heading,
	Text,
	Badge,
	KeyValue,
	Stat,
	Table,
	List,
	Image,
	Link,
	Progress,
	Alert,
	Code,
	Chart,
	Accordion,
	Avatar,
	Button,
	Tabs,
};

/** Names the agent can use, exported for the tool description / prompt. */
export const GENERATIVE_UI_COMPONENTS = Object.keys(ALLOWLIST);

function Fallback({ component }: { component: string }) {
	return (
		<span className="text-muted-foreground rounded border border-dashed px-1.5 py-0.5 text-xs">
			Unsupported UI component: {component}
		</span>
	);
}

/** Render a generative-ui spec via assistant-ui's NATIVE renderer
 * (MessagePrimitive.GenerativeUI), resolving component names against our
 * allowlist (the security boundary; unknown names hit Fallback). Streams
 * progressively as the spec fills in. */
export function GenerativeUI({ spec }: { spec: GenerativeUISpec }) {
	if (!spec?.root) return null;
	return (
		<div className="my-1 flex flex-col gap-2">
			<MessagePrimitive.GenerativeUI
				components={ALLOWLIST}
				spec={spec}
				Fallback={Fallback}
			/>
		</div>
	);
}
