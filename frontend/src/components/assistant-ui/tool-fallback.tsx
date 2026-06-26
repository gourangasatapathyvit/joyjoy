"use client";

import {
	type ToolCallMessagePartComponent,
	type ToolCallMessagePartStatus,
	useScrollLock,
	useToolCallElapsed,
} from "@assistant-ui/react";
import {
	AlertCircleIcon,
	CheckIcon,
	ChevronDownIcon,
	LoaderIcon,
	XCircleIcon,
} from "lucide-react";
import { memo, useCallback, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import {
	ToolApprovalControls,
	ToolFallbackApproval,
	useToolNeedsAction,
} from "./tool-approval";

const ANIMATION_DURATION = 200;

export type ToolFallbackRootProps = Omit<
	React.ComponentProps<typeof Collapsible>,
	"open" | "onOpenChange"
> & {
	open?: boolean;
	onOpenChange?: (open: boolean) => void;
	defaultOpen?: boolean;
};

function ToolFallbackRoot({
	className,
	open: controlledOpen,
	onOpenChange: controlledOnOpenChange,
	defaultOpen = false,
	children,
	...props
}: ToolFallbackRootProps) {
	const collapsibleRef = useRef<HTMLDivElement>(null);
	const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultOpen);
	const lockScroll = useScrollLock(collapsibleRef, ANIMATION_DURATION);

	const isControlled = controlledOpen !== undefined;
	const isOpen = isControlled ? controlledOpen : uncontrolledOpen;

	const handleOpenChange = useCallback(
		(open: boolean) => {
			lockScroll();
			if (!isControlled) {
				setUncontrolledOpen(open);
			}
			controlledOnOpenChange?.(open);
		},
		[lockScroll, isControlled, controlledOnOpenChange],
	);

	return (
		<Collapsible
			ref={collapsibleRef}
			data-slot="tool-fallback-root"
			open={isOpen}
			onOpenChange={handleOpenChange}
			className={cn(
				"aui-tool-fallback-root group/tool-fallback-root w-full",
				className,
			)}
			style={
				{
					"--animation-duration": `${ANIMATION_DURATION}ms`,
				} as React.CSSProperties
			}
			{...props}
		>
			{children}
		</Collapsible>
	);
}

type ToolStatus = ToolCallMessagePartStatus["type"];

const statusIconMap: Record<ToolStatus, React.ElementType> = {
	running: LoaderIcon,
	complete: CheckIcon,
	incomplete: XCircleIcon,
	"requires-action": AlertCircleIcon,
};

const formatToolDuration = (ms: number) => {
	if (ms < 1000) return "<1s";
	const seconds = ms / 1000;
	if (seconds < 10) return `${(Math.floor(seconds * 10) / 10).toFixed(1)}s`;
	if (seconds < 60) return `${Math.floor(seconds)}s`;
	return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
};

function ToolFallbackDuration({
	className,
	...props
}: React.ComponentProps<"span">) {
	const elapsedMs = useToolCallElapsed();
	if (elapsedMs === undefined) return null;

	return (
		<span
			data-slot="tool-fallback-duration"
			className={cn(
				"aui-tool-fallback-duration text-muted-foreground text-xs tabular-nums",
				className,
			)}
			{...props}
		>
			{formatToolDuration(elapsedMs)}
		</span>
	);
}

function ToolFallbackTrigger({
	toolName,
	status,
	className,
	...props
}: React.ComponentProps<typeof CollapsibleTrigger> & {
	toolName: string;
	status?: ToolCallMessagePartStatus;
}) {
	const { t } = useTranslation();
	const statusType = status?.type ?? "complete";
	const isRunning = statusType === "running";
	const isCancelled =
		status?.type === "incomplete" && status.reason === "cancelled";

	const Icon = statusIconMap[statusType];
	const label = isCancelled ? t("tools.cancelled") : t("tools.used");

	return (
		<CollapsibleTrigger
			data-slot="tool-fallback-trigger"
			className={cn(
				"aui-tool-fallback-trigger group/trigger text-muted-foreground hover:text-foreground flex w-fit items-center gap-2 py-1 text-sm transition-colors",
				className,
			)}
			{...props}
		>
			<Icon
				data-slot="tool-fallback-trigger-icon"
				className={cn(
					"aui-tool-fallback-trigger-icon size-4 shrink-0",
					isCancelled && "text-muted-foreground",
					isRunning && "animate-spin",
				)}
			/>
			<span
				data-slot="tool-fallback-trigger-label"
				className={cn(
					"aui-tool-fallback-trigger-label-wrapper relative inline-block text-start leading-none",
					isCancelled && "text-muted-foreground line-through",
				)}
			>
				<span>
					{label}: <b>{toolName}</b>
				</span>
				{isRunning && (
					<span
						aria-hidden
						data-slot="tool-fallback-trigger-shimmer"
						className="aui-tool-fallback-trigger-shimmer shimmer pointer-events-none absolute inset-0 motion-reduce:animate-none"
					>
						{label}: <b>{toolName}</b>
					</span>
				)}
			</span>
			<ToolFallbackDuration />
			<ChevronDownIcon
				data-slot="tool-fallback-trigger-chevron"
				className={cn(
					"aui-tool-fallback-trigger-chevron size-4 shrink-0",
					"transition-transform duration-(--animation-duration) ease-out",
					"group-data-[state=closed]/trigger:-rotate-90",
					"group-data-[state=open]/trigger:rotate-0",
				)}
			/>
		</CollapsibleTrigger>
	);
}

function ToolFallbackContent({
	className,
	children,
	...props
}: React.ComponentProps<typeof CollapsibleContent>) {
	return (
		<CollapsibleContent
			data-slot="tool-fallback-content"
			className={cn(
				"aui-tool-fallback-content relative overflow-hidden text-sm outline-none",
				"group/collapsible-content ease-out",
				"data-[state=closed]:animate-collapsible-up",
				"data-[state=open]:animate-collapsible-down",
				"data-[state=closed]:fill-mode-forwards",
				"data-[state=closed]:pointer-events-none",
				"data-[state=open]:duration-(--animation-duration)",
				"data-[state=closed]:duration-(--animation-duration)",
				className,
			)}
			{...props}
		>
			<div className="flex flex-col gap-2 ps-6 pt-1 pb-2">{children}</div>
		</CollapsibleContent>
	);
}

function ToolFallbackArgs({
	argsText,
	className,
	...props
}: React.ComponentProps<"div"> & {
	argsText?: string;
}) {
	if (!argsText) return null;

	return (
		<div
			data-slot="tool-fallback-args"
			className={cn("aui-tool-fallback-args", className)}
			{...props}
		>
			<pre className="aui-tool-fallback-args-value bg-muted/50 text-muted-foreground rounded-md p-2.5 text-xs whitespace-pre-wrap">
				{argsText}
			</pre>
		</div>
	);
}

// If the result is (or is a string encoding) a JSON array/object, return the
// parsed value so it can be rendered structurally; otherwise return as-is.
function coerceStructured(result: unknown): unknown {
	if (result !== null && typeof result === "object") return result;
	if (typeof result === "string") {
		const t = result.trim();
		if (t.startsWith("{") || t.startsWith("[")) {
			try {
				return JSON.parse(t);
			} catch {
				/* not JSON — fall through to text */
			}
		}
	}
	return result;
}

function cellText(v: unknown): string {
	if (v === null || v === undefined) return "";
	if (typeof v === "object") return JSON.stringify(v);
	return String(v);
}

/** Render a tool result: a table for an array of uniform objects, a key/value
 * table for a single object, a list for a primitive array, and otherwise the
 * raw text. Lets every tool on the generic fallback (notably MCP tools that
 * return JSON) display readably instead of as one JSON blob. */
function StructuredResult({ result }: { result: unknown }) {
	const data = coerceStructured(result);
	const Box = "max-h-96 overflow-auto rounded-md border text-xs";

	// Array of plain objects → table.
	if (
		Array.isArray(data) &&
		data.length > 0 &&
		data.every((x) => x !== null && typeof x === "object" && !Array.isArray(x))
	) {
		const cols: string[] = [];
		for (const row of data as Record<string, unknown>[])
			for (const k of Object.keys(row)) if (!cols.includes(k)) cols.push(k);
		if (cols.length > 0 && cols.length <= 12) {
			return (
				<div className={Box}>
					<table className="w-full border-collapse">
						<thead>
							<tr className="bg-muted/50 text-left">
								{cols.map((c) => (
									<th key={c} className="border-b px-2 py-1 font-medium">
										{c}
									</th>
								))}
							</tr>
						</thead>
						<tbody>
							{(data as Record<string, unknown>[]).map((row, i) => (
								// biome-ignore lint/suspicious/noArrayIndexKey: static result snapshot, never reordered
								<tr key={i} className="border-b last:border-0 align-top">
									{cols.map((c) => (
										<td key={c} className="px-2 py-1 whitespace-pre-wrap">
											{cellText(row[c])}
										</td>
									))}
								</tr>
							))}
						</tbody>
					</table>
				</div>
			);
		}
	}

	// Single object → key/value table.
	if (data !== null && typeof data === "object" && !Array.isArray(data)) {
		const entries = Object.entries(data as Record<string, unknown>);
		if (entries.length > 0) {
			return (
				<div className={Box}>
					<table className="w-full border-collapse">
						<tbody>
							{entries.map(([k, v]) => (
								<tr key={k} className="border-b align-top last:border-0">
									<td className="bg-muted/50 px-2 py-1 font-medium whitespace-nowrap">
										{k}
									</td>
									<td className="px-2 py-1 whitespace-pre-wrap">
										{cellText(v)}
									</td>
								</tr>
							))}
						</tbody>
					</table>
				</div>
			);
		}
	}

	// Array of primitives → simple list.
	if (Array.isArray(data) && data.length > 0) {
		return (
			<div className={cn(Box, "bg-muted/30 px-2.5 py-1 font-mono")}>
				{(data as unknown[]).map((v, i) => (
					// biome-ignore lint/suspicious/noArrayIndexKey: static result snapshot, never reordered
					<div key={i} className="whitespace-pre-wrap">
						{cellText(v)}
					</div>
				))}
			</div>
		);
	}

	// Anything else → text.
	return (
		<pre className="aui-tool-fallback-result-content bg-muted/50 text-muted-foreground mt-1 rounded-md p-2.5 text-xs whitespace-pre-wrap">
			{typeof result === "string" ? result : JSON.stringify(result, null, 2)}
		</pre>
	);
}

function ToolFallbackResult({
	result,
	className,
	...props
}: React.ComponentProps<"div"> & {
	result?: unknown;
}) {
	if (result === undefined) return null;

	return (
		<div
			data-slot="tool-fallback-result"
			className={cn("aui-tool-fallback-result", className)}
			{...props}
		>
			<p className="aui-tool-fallback-result-header text-muted-foreground text-xs font-medium">
				Result:
			</p>
			<div className="mt-1">
				<StructuredResult result={result} />
			</div>
		</div>
	);
}

function ToolFallbackError({
	status,
	className,
	...props
}: React.ComponentProps<"div"> & {
	status?: ToolCallMessagePartStatus;
}) {
	const { t } = useTranslation();
	if (status?.type !== "incomplete") return null;

	const error = status.error;
	const errorText = error
		? typeof error === "string"
			? error
			: JSON.stringify(error)
		: null;

	if (!errorText) return null;

	const isCancelled = status.reason === "cancelled";
	const headerText = isCancelled
		? t("tools.cancelledReason")
		: t("tools.errorLabel");

	return (
		<div
			data-slot="tool-fallback-error"
			className={cn("aui-tool-fallback-error", className)}
			{...props}
		>
			<p className="aui-tool-fallback-error-header text-muted-foreground font-semibold">
				{headerText}
			</p>
			<p className="aui-tool-fallback-error-reason text-muted-foreground">
				{errorText}
			</p>
		</div>
	);
}

const ToolFallbackImpl: ToolCallMessagePartComponent = (part) => {
	const {
		toolCallId,
		toolName,
		argsText,
		result,
		status,
		addResult,
		resume,
		interrupt,
		approval,
		respondToApproval,
	} = part;

	const isCancelled =
		status?.type === "incomplete" && status.reason === "cancelled";
	// Auto-open while awaiting approval (native interrupt OR joyjoy pending).
	const needsAction = useToolNeedsAction(toolCallId, status?.type);

	const [open, setOpen] = useState(needsAction);
	const [prevNeedsAction, setPrevNeedsAction] = useState(needsAction);
	if (needsAction !== prevNeedsAction) {
		setPrevNeedsAction(needsAction);
		if (needsAction) setOpen(true);
	}

	return (
		<ToolFallbackRoot open={open} onOpenChange={setOpen}>
			<ToolFallbackTrigger toolName={toolName} status={status} />
			<ToolFallbackContent>
				<ToolFallbackError status={status} />
				<ToolFallbackArgs
					argsText={argsText}
					className={cn(isCancelled && "opacity-60")}
				/>
				<ToolApprovalControls
					toolCallId={toolCallId}
					status={status}
					addResult={addResult}
					resume={resume}
					interrupt={interrupt}
					approval={approval}
					respondToApproval={respondToApproval}
				/>
				{!isCancelled && <ToolFallbackResult result={result} />}
			</ToolFallbackContent>
		</ToolFallbackRoot>
	);
};

const ToolFallback = memo(
	ToolFallbackImpl,
) as unknown as ToolCallMessagePartComponent & {
	Root: typeof ToolFallbackRoot;
	Trigger: typeof ToolFallbackTrigger;
	Content: typeof ToolFallbackContent;
	Args: typeof ToolFallbackArgs;
	Result: typeof ToolFallbackResult;
	Error: typeof ToolFallbackError;
	Approval: typeof ToolFallbackApproval;
};

ToolFallback.displayName = "ToolFallback";
ToolFallback.Root = ToolFallbackRoot;
ToolFallback.Trigger = ToolFallbackTrigger;
ToolFallback.Content = ToolFallbackContent;
ToolFallback.Args = ToolFallbackArgs;
ToolFallback.Result = ToolFallbackResult;
ToolFallback.Error = ToolFallbackError;
ToolFallback.Approval = ToolFallbackApproval;

export {
	ToolFallback,
	ToolFallbackApproval,
	ToolFallbackArgs,
	ToolFallbackContent,
	ToolFallbackError,
	ToolFallbackResult,
	ToolFallbackRoot,
	ToolFallbackTrigger,
};
