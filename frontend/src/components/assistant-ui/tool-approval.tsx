"use client";

// Shared approval controls for tool-call renderers. Factored out of
// `tool-fallback.tsx` so the generic fallback AND the bespoke per-tool UIs
// (execute / write_file / edit_file in `tool-uis.tsx`) all render IDENTICAL,
// correctly-wired Allow/Deny controls — i.e. moving a tool to a custom UI never
// silently drops its HITL gate.
//
// joyjoy gates tools via TWO independent paths and this component covers both:
//   1. assistant-ui's native `requires-action` interrupt → `ToolFallbackApproval`.
//   2. joyjoy's backend runs-API approval queue → `JoyApprovalBar` (keyed by
//      toolCallId via the `useApprovals()` context).

import type {
	ToolApprovalOption,
	ToolCallMessagePart,
	ToolCallMessagePartProps,
} from "@assistant-ui/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useApprovals } from "@/runtime/JoyjoyRuntimeProvider";
import { useChatStore } from "@/store/chat";

// Tool-RESULT payloads that flow back to the model — kept English (consistent
// model-facing content), NOT translated like UI chrome.
const APPROVED_RESULT = "Approved by user";
const DENIED_RESULT = "User denied tool execution";

// Maps an approval kind to its i18n key for the button label.
const APPROVAL_OPTION_KEYS: Record<string, string> = {
	"allow-once": "tools.allow",
	"allow-always": "tools.allowAlways",
	"reject-once": "tools.deny",
	"reject-always": "tools.denyAlways",
};

const isAllowKind = (kind: string) =>
	kind === "allow-once" || kind === "allow-always";

const approvalOptionLabel = (
	option: ToolApprovalOption,
	t: (key: string) => string,
) =>
	option.label ??
	(Object.hasOwn(APPROVAL_OPTION_KEYS, option.kind)
		? t(APPROVAL_OPTION_KEYS[option.kind] as string)
		: undefined) ??
	option.id;

/** assistant-ui native approval bar (the `requires-action` interrupt path). */
export function ToolFallbackApproval({
	className,
	addResult,
	resume,
	interrupt,
	approval,
	respondToApproval,
	...props
}: React.ComponentProps<"div"> &
	Partial<
		Pick<ToolCallMessagePartProps, "addResult" | "resume" | "respondToApproval">
	> & {
		interrupt?: ToolCallMessagePart["interrupt"];
		approval?: ToolCallMessagePart["approval"];
	}) {
	const [submitted, setSubmitted] = useState(false);
	const [confirmingId, setConfirmingId] = useState<string | null>(null);
	const { t } = useTranslation();

	if (
		approval != null &&
		(approval.approved !== undefined || approval.resolution !== undefined)
	)
		return null;

	// Custom (`_`-prefixed) kinds cannot be resolved to a boolean by the kit;
	// hosts using custom kinds render their own bar. A declared option list is
	// a host constraint: the kit never adds an approval path beyond it, but
	// always preserves a refusal path.
	const declaredOptions = respondToApproval ? approval?.options : undefined;
	const options = declaredOptions?.filter((o) =>
		Object.hasOwn(APPROVAL_OPTION_KEYS, o.kind),
	);

	const respond = (approved: boolean) => {
		if (submitted) return;
		if (
			approval != null &&
			approval.approved === undefined &&
			respondToApproval
		) {
			respondToApproval({ approved });
		} else if (interrupt) {
			resume?.({ approved });
		} else {
			addResult?.(approved ? APPROVED_RESULT : DENIED_RESULT);
		}
		setSubmitted(true);
	};

	const respondWithOption = (option: ToolApprovalOption) => {
		if (submitted) return;
		respondToApproval?.({ optionId: option.id });
		setSubmitted(true);
		setConfirmingId(null);
	};

	const handleOption = (option: ToolApprovalOption) => {
		if (option.confirm) {
			setConfirmingId(option.id);
		} else {
			respondWithOption(option);
		}
	};

	const confirming =
		confirmingId != null
			? options?.find((o) => o.id === confirmingId)
			: undefined;

	if (confirming) {
		const confirmMeta =
			typeof confirming.confirm === "object" ? confirming.confirm : undefined;
		const confirmDescription =
			confirmMeta?.description ?? confirming.description;
		return (
			<div
				data-slot="tool-fallback-approval-confirm"
				className={cn(
					"aui-tool-fallback-approval-confirm flex flex-col gap-2 pt-1",
					className,
				)}
				{...props}
			>
				<p className="aui-tool-fallback-approval-confirm-title font-semibold">
					{confirmMeta?.title ?? `${approvalOptionLabel(confirming, t)}?`}
				</p>
				{confirmDescription && (
					<p className="aui-tool-fallback-approval-confirm-description text-muted-foreground">
						{confirmDescription}
					</p>
				)}
				{confirming.grants && confirming.grants.length > 0 && (
					<ul className="aui-tool-fallback-approval-confirm-grants flex flex-col gap-1">
						{confirming.grants.map((grant) => (
							<li key={grant}>
								<code className="aui-tool-fallback-approval-confirm-grant bg-muted rounded px-1.5 py-0.5 text-xs">
									{grant}
								</code>
							</li>
						))}
					</ul>
				)}
				<div className="flex items-center gap-2">
					<Button
						size="sm"
						onClick={() => respondWithOption(confirming)}
						disabled={submitted}
					>
						Confirm
					</Button>
					<Button
						size="sm"
						variant="outline"
						onClick={() => setConfirmingId(null)}
						disabled={submitted}
					>
						Back
					</Button>
				</div>
			</div>
		);
	}

	if (declaredOptions && declaredOptions.length > 0) {
		const allowOptions = options?.filter((o) => isAllowKind(o.kind)) ?? [];
		const rejectOptions = options?.filter((o) => !isAllowKind(o.kind)) ?? [];
		return (
			<div
				data-slot="tool-fallback-approval"
				className={cn(
					"aui-tool-fallback-approval flex flex-wrap items-center gap-2 pt-1",
					className,
				)}
				{...props}
			>
				{[...allowOptions, ...rejectOptions].map((option) => (
					<Button
						key={option.id}
						size="sm"
						variant={option === allowOptions[0] ? "default" : "outline"}
						onClick={() => handleOption(option)}
						disabled={submitted}
					>
						{approvalOptionLabel(option, t)}
					</Button>
				))}
				{rejectOptions.length === 0 && (
					<Button
						size="sm"
						variant="outline"
						onClick={() => respond(false)}
						disabled={submitted}
					>
						Deny
					</Button>
				)}
			</div>
		);
	}

	return (
		<div
			data-slot="tool-fallback-approval"
			className={cn(
				"aui-tool-fallback-approval flex items-center gap-2 pt-1",
				className,
			)}
			{...props}
		>
			<Button size="sm" onClick={() => respond(true)} disabled={submitted}>
				Allow
			</Button>
			<Button
				size="sm"
				variant="outline"
				onClick={() => respond(false)}
				disabled={submitted}
			>
				Deny
			</Button>
		</div>
	);
}

/** joyjoy backend HITL bar — resolves the pending approval keyed by toolCallId
 * through the runs-API approval queue (`useApprovals`). */
export function JoyApprovalBar({ toolCallId }: { toolCallId: string }) {
	const { t } = useTranslation();
	const { respond } = useApprovals();
	const setAutoApprove = useChatStore((s) => s.setAutoApprove);
	return (
		<div className="aui-tool-fallback-approval flex flex-wrap items-center gap-2 pt-1">
			<Button size="sm" onClick={() => respond(toolCallId, "approve")}>
				{t("tools.allowOnce")}
			</Button>
			<Button
				size="sm"
				variant="outline"
				onClick={() => {
					// Approve this call and stop asking for the rest of the chat.
					setAutoApprove(true);
					respond(toolCallId, "approve");
				}}
			>
				{t("tools.allowSession")}
			</Button>
			<Button
				size="sm"
				variant="outline"
				onClick={() => respond(toolCallId, "reject")}
			>
				{t("tools.deny")}
			</Button>
		</div>
	);
}

type ToolApprovalControlsProps = Partial<
	Pick<
		ToolCallMessagePartProps,
		"toolCallId" | "status" | "addResult" | "resume" | "respondToApproval"
	>
> & {
	interrupt?: ToolCallMessagePart["interrupt"];
	approval?: ToolCallMessagePart["approval"];
};

/** Drop-in approval controls for ANY tool-call renderer. Renders the native
 * `requires-action` bar and/or the joyjoy pending bar as applicable — renders
 * nothing when no approval is pending, so it's always safe to include. */
export function ToolApprovalControls(props: ToolApprovalControlsProps) {
	const { toolCallId, status } = props;
	const { pending } = useApprovals();
	const isRequiresAction = status?.type === "requires-action";
	const joyPending = toolCallId ? pending[toolCallId] : undefined;
	return (
		<>
			{isRequiresAction && (
				<ToolFallbackApproval
					addResult={props.addResult}
					resume={props.resume}
					interrupt={props.interrupt}
					approval={props.approval}
					respondToApproval={props.respondToApproval}
				/>
			)}
			{joyPending && toolCallId && <JoyApprovalBar toolCallId={toolCallId} />}
		</>
	);
}

/** True when this tool call is awaiting any kind of approval (native interrupt
 * or joyjoy pending) — used to auto-open the collapsible. */
export function useToolNeedsAction(
	toolCallId: string | undefined,
	statusType: string | undefined,
): boolean {
	const { pending } = useApprovals();
	const joyPending = toolCallId ? !!pending[toolCallId] : false;
	return statusType === "requires-action" || joyPending;
}
