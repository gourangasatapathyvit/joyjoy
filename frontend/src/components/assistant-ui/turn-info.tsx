"use client";

// Context Display badge + Sources footer, both driven by live run telemetry the
// backend emits over the run SSE stream (usage / sources events → chat store).
// The built-in assistant-ui Context Display is AI-SDK-coupled (useThreadTokenUsage),
// so this is a small custom badge fed by our external-store usage events.

import { FileTextIcon } from "lucide-react";
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/store/chat";

// Approximate context windows by model-name substring (total context budget).
// Only used to render a "how full is the context" %; the token counts themselves
// come from the model's reported usage_metadata, so this map is best-effort.
const CONTEXT_WINDOWS: [RegExp, number][] = [
	[/gpt-4\.1/i, 1_047_576],
	[/gpt-4o|gpt-4-turbo/i, 128_000],
	[/gpt-5/i, 400_000],
	[/\bo[134]\b|o3|o4-mini/i, 200_000],
	[/claude/i, 200_000],
	[/gemini-1\.5-pro/i, 2_000_000],
	[/gemini/i, 1_000_000],
];

function contextWindowFor(model: string): number | null {
	for (const [re, n] of CONTEXT_WINDOWS) if (re.test(model)) return n;
	return null;
}

function fmtTokens(n: number): string {
	if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
	if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
	return `${n}`;
}

function safeHost(url: string): string {
	try {
		return new URL(url).hostname.replace(/^www\./, "");
	} catch {
		return url;
	}
}

// SVG donut ring geometry (matches the assistant-ui Context Display "Ring"
// preset — a 20px ring whose arc fills with context usage).
const RING_SIZE = 20;
const RING_STROKE = 2.5;
const RING_RADIUS = (RING_SIZE - RING_STROKE) / 2;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

function strokeColorFor(percent: number): string {
	if (percent > 85) return "stroke-red-500";
	if (percent >= 65) return "stroke-amber-500";
	return "stroke-emerald-500";
}

function UsageRow({ label, value }: { label: string; value: string }) {
	return (
		<div className="flex items-center justify-between gap-4">
			<span className="text-muted-foreground">{label}</span>
			<span className="font-mono tabular-nums">{value}</span>
		</div>
	);
}

/** Context Display "Ring" — an SVG donut whose arc + color reflect how full the
 * model context is. On hover it reveals a token breakdown (usage %, input,
 * cached, output, reasoning, total), like assistant-ui's Context Display. Fed by
 * our external-store run telemetry rather than the AI-SDK-coupled built-in. */
export function ContextBadge() {
	const usage = useChatStore((s) => s.usage);
	const model = useChatStore((s) => s.model);

	// Current context fill = the latest call's input tokens (falls back to total).
	const used = usage?.input_tokens ?? usage?.total_tokens ?? 0;
	if (!used) return null;

	const cw = contextWindowFor(model);
	const percent = cw ? Math.min(100, (used / cw) * 100) : 0;
	const dashoffset = RING_CIRCUMFERENCE - (percent / 100) * RING_CIRCUMFERENCE;

	return (
		<TooltipProvider delay={0}>
			<Tooltip>
				<TooltipTrigger
					render={
						<button
							type="button"
							aria-label="Context usage"
							className="hover:bg-accent inline-flex items-center rounded-md p-0.5 transition-colors"
						/>
					}
				>
					<svg
						aria-hidden="true"
						width={RING_SIZE}
						height={RING_SIZE}
						viewBox={`0 0 ${RING_SIZE} ${RING_SIZE}`}
						className="-rotate-90"
					>
						<circle
							cx={RING_SIZE / 2}
							cy={RING_SIZE / 2}
							r={RING_RADIUS}
							fill="none"
							strokeWidth={RING_STROKE}
							className="stroke-muted"
						/>
						<circle
							cx={RING_SIZE / 2}
							cy={RING_SIZE / 2}
							r={RING_RADIUS}
							fill="none"
							strokeWidth={RING_STROKE}
							strokeLinecap="round"
							strokeDasharray={RING_CIRCUMFERENCE}
							strokeDashoffset={dashoffset}
							className={cn(
								"transition-[stroke-dashoffset,stroke] duration-300",
								cw ? strokeColorFor(percent) : "stroke-muted-foreground/50",
							)}
						/>
					</svg>
				</TooltipTrigger>
				<TooltipContent
					side="top"
					// Match the arrow to the popover body (the shared tooltip's arrow
					// defaults to the inverted foreground color, which clashes here).
					className="bg-popover text-popover-foreground rounded-lg border px-3 py-2 shadow-md [&_[data-slot=tooltip-arrow]]:bg-popover [&_[data-slot=tooltip-arrow]]:fill-popover"
				>
					<div className="grid min-w-40 gap-1.5 text-xs">
						{cw ? (
							<UsageRow label="Usage" value={`${Math.round(percent)}%`} />
						) : null}
						{usage?.input_tokens !== undefined && (
							<UsageRow label="Input" value={fmtTokens(usage.input_tokens)} />
						)}
						{usage?.cached_input_tokens ? (
							<UsageRow
								label="Cached"
								value={fmtTokens(usage.cached_input_tokens)}
							/>
						) : null}
						{usage?.output_tokens !== undefined && (
							<UsageRow label="Output" value={fmtTokens(usage.output_tokens)} />
						)}
						{usage?.reasoning_tokens ? (
							<UsageRow
								label="Reasoning"
								value={fmtTokens(usage.reasoning_tokens)}
							/>
						) : null}
						<div className="mt-0.5 border-t pt-1.5">
							<UsageRow
								label="Total"
								value={
									cw ? `${fmtTokens(used)} / ${fmtTokens(cw)}` : fmtTokens(used)
								}
							/>
						</div>
					</div>
				</TooltipContent>
			</Tooltip>
		</TooltipProvider>
	);
}

/** Citation chips for the most recent answer — URL sources link out (by host),
 * document sources show a file chip. Driven by the run's `sources` event. */
export function TurnSources({ messageId }: { messageId: string }) {
	const sources = useChatStore((s) => s.sourcesByMessage[messageId]);
	if (!sources?.length) return null;

	return (
		<div className="mt-1 mb-1 flex flex-col gap-1 px-2">
			<span className="text-muted-foreground text-xs font-medium">Sources</span>
			<div className="flex flex-wrap gap-1.5">
				{sources.map((s) =>
					s.sourceType === "url" && s.url ? (
						<a
							key={s.url}
							href={s.url}
							target="_blank"
							rel="noopener noreferrer"
							className="bg-muted hover:bg-accent text-foreground inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs transition-colors"
							title={s.title ?? s.url}
						>
							{/* Favicon via Google's s2 service (works for any domain), like
							    the source chips in Google's AI mode. */}
							<img
								src={`https://www.google.com/s2/favicons?domain=${safeHost(s.url)}&sz=64`}
								alt=""
								className="size-4 shrink-0 rounded-sm"
							/>
							<span className="max-w-50 truncate">{safeHost(s.url)}</span>
						</a>
					) : (
						<span
							key={s.name ?? s.title ?? "doc"}
							className="bg-muted text-foreground inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs"
							title={s.title ?? s.name}
						>
							<FileTextIcon className="size-3 shrink-0" />
							<span className="max-w-50 truncate">
								{s.name ?? s.title ?? "document"}
							</span>
						</span>
					),
				)}
			</div>
		</div>
	);
}
