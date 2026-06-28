import {
	ActionBarMorePrimitive,
	ActionBarPrimitive,
	type AssistantState,
	AuiIf,
	BranchPickerPrimitive,
	ComposerPrimitive,
	ErrorPrimitive,
	groupPartByType,
	MessagePrimitive,
	SuggestionPrimitive,
	ThreadPrimitive,
	type ToolCallMessagePartComponent,
	useAuiState,
} from "@assistant-ui/react";
import {
	ArrowDownIcon,
	ArrowUpIcon,
	CheckIcon,
	ChevronLeftIcon,
	ChevronRightIcon,
	CopyIcon,
	DownloadIcon,
	Loader2Icon,
	MicIcon,
	MoreHorizontalIcon,
	PencilIcon,
	RefreshCwIcon,
	SquareIcon,
	Volume2Icon,
} from "lucide-react";
import {
	type ComponentType,
	createContext,
	type FC,
	type PropsWithChildren,
	type ReactNode,
	useContext,
	useState,
} from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import {
	ComposerAddAttachment,
	ComposerAttachments,
	UserMessageAttachments,
} from "@/components/assistant-ui/attachment";
import { ComposerTriggers } from "@/components/assistant-ui/composer-triggers";
import {
	DotMatrix,
	type DotMatrixState,
} from "@/components/assistant-ui/dot-matrix";
import { MarkdownText } from "@/components/assistant-ui/markdown-text";
import { MediaFile, MediaImage } from "@/components/assistant-ui/media-part";
import {
	ComposerQuotePreview,
	QuoteBlock,
	SelectionToolbar,
} from "@/components/assistant-ui/quote";
import {
	Reasoning,
	ReasoningContent,
	ReasoningRoot,
	ReasoningText,
	ReasoningTrigger,
} from "@/components/assistant-ui/reasoning";
import { ToolFallback } from "@/components/assistant-ui/tool-fallback";
import {
	ToolGroupContent,
	ToolGroupRoot,
	ToolGroupTrigger,
} from "@/components/assistant-ui/tool-group";
import { TOOL_UIS } from "@/components/assistant-ui/tool-uis";
import { TooltipIconButton } from "@/components/assistant-ui/tooltip-icon-button";
import { ContextBadge, TurnSources } from "@/components/assistant-ui/turn-info";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useApprovals } from "@/runtime/JoyjoyRuntimeProvider";
import { useSettingsStore } from "@/store/settings";

// Tool-call group that auto-expands while a HITL approval is pending in the
// ACTIVE (not-yet-complete) group, so the Allow / Deny buttons are visible
// without a manual expand. Historical (complete) groups are untouched, and the
// user can still collapse/expand any group freely once it's open.
function ApprovalAwareToolGroup({
	count,
	statusType,
	defaultOpen,
	children,
}: {
	count: number;
	statusType: string;
	defaultOpen: boolean;
	children: ReactNode;
}) {
	const { hasPending } = useApprovals();
	const forceOpen = hasPending && statusType !== "complete";
	const [open, setOpen] = useState(defaultOpen || forceOpen);
	const [prevForceOpen, setPrevForceOpen] = useState(forceOpen);
	if (forceOpen !== prevForceOpen) {
		setPrevForceOpen(forceOpen);
		if (forceOpen) setOpen(true);
	}
	return (
		<ToolGroupRoot variant="ghost" open={open} onOpenChange={setOpen}>
			<ToolGroupTrigger count={count} active={statusType === "running"} />
			<ToolGroupContent>{children}</ToolGroupContent>
		</ToolGroupRoot>
	);
}

export type ThreadGroupPart = MessagePrimitive.GroupedParts.GroupPart;

/**
 * Optional component overrides for the thread. `AssistantMessage` and
 * `Welcome` replace whole sections; the remaining slots override how the
 * assistant message renders tool calls and part groups. Tool UIs registered
 * by name (toolkit `render`, `useAssistantDataUI`) take precedence over
 * `ToolFallback`.
 */
export type ThreadComponents = {
	AssistantMessage?: ComponentType | undefined;
	Welcome?: ComponentType | undefined;
	ToolFallback?: ToolCallMessagePartComponent | undefined;
	ToolGroup?:
		| ComponentType<PropsWithChildren<{ group: ThreadGroupPart }>>
		| undefined;
	ReasoningGroup?:
		| ComponentType<PropsWithChildren<{ group: ThreadGroupPart }>>
		| undefined;
};

export type ThreadProps = {
	components?: ThreadComponents | undefined;
};

const EMPTY_COMPONENTS: ThreadComponents = {};

const ThreadComponentsContext =
	createContext<ThreadComponents>(EMPTY_COMPONENTS);

// Startup exposes a loading placeholder thread; treat it as a new chat so
// the composer mounts centered. Loads after startup keep the docked layout.
const isNewChatView = (s: AssistantState) =>
	s.thread.messages.length === 0 &&
	(!s.thread.isLoading || s.threads.isLoading);

export const Thread: FC<ThreadProps> = ({ components = EMPTY_COMPONENTS }) => {
	const isEmpty = useAuiState(isNewChatView);

	return (
		<ThreadComponentsContext.Provider value={components}>
			<ThreadRoot isEmpty={isEmpty} />
		</ThreadComponentsContext.Provider>
	);
};

const ThreadRoot: FC<{ isEmpty: boolean }> = ({ isEmpty }) => {
	const { t } = useTranslation();
	const { Welcome = ThreadWelcome } = useContext(ThreadComponentsContext);
	const autoFollow = useSettingsStore((s) => s.autoFollow);

	return (
		<ThreadPrimitive.Root
			className="aui-root aui-thread-root bg-background @container flex h-full flex-col"
			style={{
				["--thread-max-width" as string]: "44rem",
				["--composer-bg" as string]:
					"color-mix(in oklab, var(--color-muted) 30%, var(--color-background))",
				["--composer-radius" as string]: "1.5rem",
				["--composer-padding" as string]: "8px",
			}}
		>
			<SelectionToolbar />
			<ThreadPrimitive.Viewport
				turnAnchor="top"
				autoScroll={autoFollow}
				data-slot="aui_thread-viewport"
				className="relative flex flex-1 flex-col overflow-x-auto overflow-y-scroll scroll-smooth"
			>
				<div
					className={cn(
						"mx-auto flex w-full max-w-(--thread-max-width) flex-1 flex-col px-4 pt-4",
						isEmpty && "justify-center",
					)}
				>
					<AuiIf condition={isNewChatView}>
						<Welcome />
					</AuiIf>

					{/* Loading a saved conversation (sidebar tap) — built-in thread.isLoading */}
					<AuiIf condition={(s) => s.thread.isLoading}>
						<div className="flex flex-1 items-center justify-center gap-2 py-16 text-muted-foreground">
							<Loader2Icon className="size-5 animate-spin" />
							<span className="text-sm">{t("common.loading")}</span>
						</div>
					</AuiIf>

					<div
						data-slot="aui_message-group"
						className="mb-14 flex flex-col gap-y-6 empty:hidden"
					>
						<ThreadPrimitive.Messages>
							{() => <ThreadMessage />}
						</ThreadPrimitive.Messages>
					</div>

					<ThreadPrimitive.ViewportFooter
						className={cn(
							"aui-thread-viewport-footer bg-background flex flex-col gap-4 overflow-visible pb-4 md:pb-6",
							!isEmpty &&
								"sticky bottom-0 mt-auto rounded-t-(--composer-radius)",
						)}
					>
						<ThreadScrollToBottom />
						<Composer />
						<AuiIf condition={(s) => isNewChatView(s) && s.composer.isEmpty}>
							<ThreadSuggestions />
						</AuiIf>
					</ThreadPrimitive.ViewportFooter>
				</div>
			</ThreadPrimitive.Viewport>
		</ThreadPrimitive.Root>
	);
};

const ThreadMessage: FC = () => {
	const { AssistantMessage: AssistantMessageComponent = AssistantMessage } =
		useContext(ThreadComponentsContext);
	const role = useAuiState((s) => s.message.role);
	const isEditing = useAuiState((s) => s.message.composer.isEditing);

	if (isEditing) return <EditComposer />;
	if (role === "user") return <UserMessage />;
	return <AssistantMessageComponent />;
};

const ThreadScrollToBottom: FC = () => {
	return (
		<ThreadPrimitive.ScrollToBottom
			render={
				<TooltipIconButton
					tooltip="Scroll to bottom"
					variant="outline"
					className="aui-thread-scroll-to-bottom dark:border-border dark:bg-background dark:hover:bg-accent absolute -top-12 z-10 self-center rounded-full p-4 disabled:invisible"
				/>
			}
		>
			<ArrowDownIcon />
		</ThreadPrimitive.ScrollToBottom>
	);
};

const ThreadWelcome: FC = () => {
	const { t } = useTranslation();
	return (
		<div className="aui-thread-welcome-root mb-6 flex flex-col items-center px-4 text-center">
			<h1 className="aui-thread-welcome-message-inner fade-in slide-in-from-bottom-1 animate-in fill-mode-both text-2xl font-semibold duration-200">
				{t("chat.welcome")}
			</h1>
		</div>
	);
};

const ThreadSuggestions: FC = () => {
	return (
		<div className="aui-thread-welcome-suggestions flex w-full flex-wrap items-center justify-center gap-2 px-4">
			<ThreadPrimitive.Suggestions>
				{() => <ThreadSuggestionItem />}
			</ThreadPrimitive.Suggestions>
		</div>
	);
};

const ThreadSuggestionItem: FC = () => {
	return (
		<div className="aui-thread-welcome-suggestion-display fade-in slide-in-from-bottom-2 animate-in fill-mode-both duration-200">
			<SuggestionPrimitive.Trigger
				send
				render={
					<Button
						variant="ghost"
						className="aui-thread-welcome-suggestion text-foreground hover:bg-muted border-border/60 h-auto gap-1.5 rounded-full border px-3.5 py-1.5 text-sm font-normal whitespace-nowrap transition-colors"
					/>
				}
			>
				<SuggestionPrimitive.Title className="aui-thread-welcome-suggestion-text-1" />
				<SuggestionPrimitive.Description className="aui-thread-welcome-suggestion-text-2 empty:hidden" />
			</SuggestionPrimitive.Trigger>
		</div>
	);
};

const Composer: FC = () => {
	const { t } = useTranslation();
	return (
		<ComposerPrimitive.Unstable_TriggerPopoverRoot>
			<div className="aui-composer-trigger-anchor relative flex w-full flex-col">
				<ComposerTriggers />
				<ComposerPrimitive.Root className="aui-composer-root relative flex w-full flex-col">
					<ComposerPrimitive.AttachmentDropzone
						render={
							<div
								data-slot="aui_composer-shell"
								className="border-border/60 data-[dragging=true]:border-ring focus-within:border-border dark:border-muted-foreground/15 dark:focus-within:border-muted-foreground/30 flex w-full flex-col gap-2 rounded-(--composer-radius) border bg-(--composer-bg) p-(--composer-padding) shadow-[0_4px_16px_-8px_rgba(0,0,0,0.08),0_1px_2px_rgba(0,0,0,0.04)] transition-[border-color,box-shadow] focus-within:shadow-[0_6px_24px_-8px_rgba(0,0,0,0.12),0_1px_2px_rgba(0,0,0,0.05)] data-[dragging=true]:border-dashed data-[dragging=true]:bg-[color-mix(in_oklab,var(--color-accent)_50%,var(--color-background))] dark:shadow-none"
							/>
						}
					>
						<ComposerAttachments />
						<ComposerQuotePreview />
						<ComposerPrimitive.Input
							placeholder={t("chat.placeholder")}
							className="aui-composer-input placeholder:text-muted-foreground/80 max-h-32 min-h-10 w-full resize-none bg-transparent px-2.5 py-1 text-base outline-none"
							rows={1}
							autoFocus
							aria-label="Message input"
						/>
						<ComposerAction />
					</ComposerPrimitive.AttachmentDropzone>
				</ComposerPrimitive.Root>
			</div>
		</ComposerPrimitive.Unstable_TriggerPopoverRoot>
	);
};

const ComposerAction: FC = () => {
	const { t } = useTranslation();
	return (
		<div className="aui-composer-action-wrapper relative flex items-center justify-between">
			<ComposerAddAttachment />
			<div className="flex items-center gap-1.5">
				{/* Context Display: token/context-fill badge, left of voice input. */}
				<ContextBadge />
				<AuiIf condition={(s) => s.thread.capabilities.dictation}>
					<AuiIf condition={(s) => s.composer.dictation == null}>
						<ComposerPrimitive.Dictate
							render={
								<TooltipIconButton
									tooltip="Voice input"
									side="bottom"
									type="button"
									variant="ghost"
									size="icon"
									className="aui-composer-dictate size-7 rounded-full"
									aria-label="Start voice input"
								/>
							}
						>
							<MicIcon className="aui-composer-dictate-icon size-4" />
						</ComposerPrimitive.Dictate>
					</AuiIf>
					<AuiIf condition={(s) => s.composer.dictation != null}>
						<ComposerPrimitive.StopDictation
							render={
								<TooltipIconButton
									tooltip="Stop dictation"
									side="bottom"
									type="button"
									variant="ghost"
									size="icon"
									className="aui-composer-stop-dictation text-destructive size-7 rounded-full"
									aria-label="Stop voice input"
								/>
							}
						>
							<SquareIcon className="aui-composer-stop-dictation-icon size-3.5 animate-pulse fill-current" />
						</ComposerPrimitive.StopDictation>
					</AuiIf>
				</AuiIf>
				<AuiIf condition={(s) => !s.thread.isRunning}>
					<ComposerPrimitive.Send
						render={
							<TooltipIconButton
								tooltip={t("chat.send")}
								side="bottom"
								type="button"
								variant="default"
								size="icon"
								className="aui-composer-send size-7 rounded-full"
								aria-label={t("chat.send")}
							/>
						}
					>
						<ArrowUpIcon className="aui-composer-send-icon size-4.5" />
					</ComposerPrimitive.Send>
				</AuiIf>
				<AuiIf condition={(s) => s.thread.isRunning}>
					<ComposerPrimitive.Cancel
						render={
							<Button
								type="button"
								variant="default"
								size="icon"
								className="aui-composer-cancel size-7 rounded-full"
								aria-label={t("chat.stop")}
							/>
						}
					>
						<SquareIcon className="aui-composer-cancel-icon size-3.5 fill-current" />
					</ComposerPrimitive.Cancel>
				</AuiIf>
			</div>
		</div>
	);
};

const MessageError: FC = () => {
	return (
		<MessagePrimitive.Error>
			<ErrorPrimitive.Root className="aui-message-error-root border-destructive bg-destructive/10 text-destructive dark:bg-destructive/5 mt-2 rounded-md border p-3 text-sm dark:text-red-200">
				<ErrorPrimitive.Message className="aui-message-error-message line-clamp-2" />
			</ErrorPrimitive.Root>
		</MessagePrimitive.Error>
	);
};

const AssistantMessage: FC = () => {
	const {
		ToolFallback: ToolFallbackComponent = ToolFallback,
		ToolGroup,
		ReasoningGroup,
	} = useContext(ThreadComponentsContext);
	const activityDisplay = useSettingsStore((s) => s.activityDisplay);
	// This message's id — keys its persisted citations (Sources footer).
	const messageId = useAuiState((s) => s.message.id);

	// reserves space for action bar and compensates with `-mb` for consistent msg spacing
	// keeps hovered action bar from shifting layout (autohide doesn't support absolute positioning well)
	// for pt-[n] use -mb-[n + 6] & min-h-[n + 6] to preserve compensation
	const ACTION_BAR_PT = "pt-1.5";
	const ACTION_BAR_HEIGHT = `-mb-7.5 min-h-7.5 ${ACTION_BAR_PT}`;

	return (
		<MessagePrimitive.Root
			data-slot="aui_assistant-message-root"
			data-role="assistant"
			// hover/focus z-lift: the footer uses a negative margin so the next
			// message overlaps its action bar by a few px — raising the hovered
			// message keeps every action-bar button fully clickable.
			className="fade-in slide-in-from-bottom-1 animate-in relative duration-150 hover:z-10 focus-within:z-10"
		>
			<div
				data-slot="aui_assistant-message-content"
				// [contain-intrinsic-size:auto_24px] fixes issue #4104, don't change without checking for regressions
				className="text-foreground px-2 leading-relaxed wrap-break-word [contain-intrinsic-size:auto_24px] [content-visibility:auto]"
			>
				<MessagePrimitive.GroupedParts
					groupBy={groupPartByType({
						reasoning: ["group-chainOfThought", "group-reasoning"],
						"tool-call": ["group-chainOfThought", "group-tool"],
						"standalone-tool-call": [],
					})}
				>
					{({ part, children }) => {
						switch (part.type) {
							case "group-chainOfThought":
								return <div data-slot="aui_chain-of-thought">{children}</div>;
							case "group-tool":
								if (ToolGroup) {
									return <ToolGroup group={part}>{children}</ToolGroup>;
								}
								return (
									<ApprovalAwareToolGroup
										count={part.indices.length}
										statusType={part.status.type}
										defaultOpen={activityDisplay === "stream"}
									>
										{children}
									</ApprovalAwareToolGroup>
								);
							case "group-reasoning": {
								if (ReasoningGroup) {
									return (
										<ReasoningGroup group={part}>{children}</ReasoningGroup>
									);
								}
								const running = part.status.type === "running";
								return (
									<ReasoningRoot streaming={running}>
										<ReasoningTrigger active={running} />
										<ReasoningContent aria-busy={running}>
											<ReasoningText>{children}</ReasoningText>
										</ReasoningContent>
									</ReasoningRoot>
								);
							}
							case "text":
								return <MarkdownText />;
							case "image":
								return (
									<MediaImage image={part.image} filename={part.filename} />
								);
							case "file":
								return (
									<MediaFile
										data={part.data}
										mimeType={part.mimeType}
										filename={part.filename}
									/>
								);
							case "reasoning":
								return <Reasoning {...part} />;
							case "tool-call": {
								// Prefer any registry-provided override, then our bespoke
								// per-tool UIs, then the generic fallback. All paths reuse
								// the same approval controls, so HITL gating is preserved.
								if (part.toolUI) return part.toolUI;
								const CustomToolUI = TOOL_UIS[part.toolName];
								return CustomToolUI ? (
									<CustomToolUI {...part} />
								) : (
									<ToolFallbackComponent {...part} />
								);
							}
							case "data":
								return part.dataRendererUI;
							case "indicator":
								return <WorkingIndicator />;
							default:
								return null;
						}
					}}
				</MessagePrimitive.GroupedParts>
				<MessageError />
			</div>

			{/* Per-answer citations, keyed to this message id (persists across reloads). */}
			<TurnSources messageId={messageId} />

			<div
				data-slot="aui_assistant-message-footer"
				className={cn("ms-2 flex items-center", ACTION_BAR_HEIGHT)}
			>
				<BranchPicker />
				<AssistantActionBar />
			</div>
		</MessagePrimitive.Root>
	);
};

// Map a running tool's name to the dot-matrix pattern that best fits the work:
// network/lookup tools sweep ("searching"), filesystem reads ripple ("syncing"),
// writes stream up ("uploading"), and code/exec twinkle ("loading").
const TOOL_STATE: { re: RegExp; state: DotMatrixState }[] = [
	{
		re: /fetch|search|web|browse|crawl|tavily|duckduckgo|http/i,
		state: "searching",
	},
	{ re: /^(read_file|ls|glob|grep|load_skill)$/i, state: "syncing" },
	{ re: /write|edit/i, state: "uploading" },
	{ re: /execute|run|code|bash|python|shell/i, state: "loading" },
];

function toolToState(name: string): DotMatrixState {
	for (const { re, state } of TOOL_STATE) if (re.test(name)) return state;
	return "loading";
}

// The assistant's "working" placeholder (shown while a turn runs before/between
// content). Replaces the old pulsing ● with assistant-ui's dot-matrix, driving
// its pattern from the live run state: a waiting ellipsis when a HITL approval
// is pending, a tool-specific pattern while a tool runs, else the thinking
// ripple.
const WorkingIndicator: FC = () => {
	const { t } = useTranslation();
	const status = useAuiState(
		(s) => s.message.status?.type as string | undefined,
	);
	const runningTool = useAuiState((s) => {
		const parts = s.message.content as unknown as ReadonlyArray<{
			type: string;
			toolName?: string;
			status?: { type?: string };
		}>;
		return parts.find(
			(p) => p.type === "tool-call" && p.status?.type === "running",
		)?.toolName;
	});
	const state: DotMatrixState =
		status === "requires-action"
			? "waiting"
			: runningTool
				? toolToState(runningTool)
				: "thinking";
	return (
		<DotMatrix state={state} label={t("chat.working")} className="size-5" />
	);
};

const AssistantActionBar: FC = () => {
	const { t } = useTranslation();
	return (
		<ActionBarPrimitive.Root
			hideWhenRunning
			autohide="not-last"
			className="aui-assistant-action-bar-root text-muted-foreground animate-in fade-in col-start-3 row-start-2 -ms-1 flex gap-1 duration-200"
		>
			<ActionBarPrimitive.Copy
				render={
					<TooltipIconButton
						tooltip="Copy"
						onClick={() => toast.success(t("chat.copied"))}
					/>
				}
			>
				<AuiIf condition={(s) => s.message.isCopied}>
					<CheckIcon className="animate-in zoom-in-50 fade-in duration-200 ease-out" />
				</AuiIf>
				<AuiIf condition={(s) => !s.message.isCopied}>
					<CopyIcon className="animate-in zoom-in-75 fade-in duration-150" />
				</AuiIf>
			</ActionBarPrimitive.Copy>
			<ActionBarPrimitive.Reload
				render={<TooltipIconButton tooltip="Refresh" />}
			>
				<RefreshCwIcon />
			</ActionBarPrimitive.Reload>
			{/* Read aloud (Web Speech TTS) — shown only while not speaking; the
			    StopSpeaking variant replaces it during playback. */}
			<ActionBarPrimitive.Speak
				render={<TooltipIconButton tooltip="Read aloud" />}
			>
				<Volume2Icon />
			</ActionBarPrimitive.Speak>
			<ActionBarPrimitive.StopSpeaking
				render={<TooltipIconButton tooltip="Stop" />}
			>
				<SquareIcon />
			</ActionBarPrimitive.StopSpeaking>
			<ActionBarMorePrimitive.Root>
				<ActionBarMorePrimitive.Trigger
					render={
						<TooltipIconButton
							tooltip="More"
							className="data-[state=open]:bg-accent"
						/>
					}
				>
					<MoreHorizontalIcon />
				</ActionBarMorePrimitive.Trigger>
				<ActionBarMorePrimitive.Content
					side="bottom"
					align="start"
					sideOffset={6}
					className="aui-action-bar-more-content bg-popover/95 text-popover-foreground data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=open]:animate-in data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=closed]:animate-out data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2 z-50 min-w-[8rem] overflow-hidden rounded-xl border p-1.5 shadow-lg backdrop-blur-sm"
				>
					<ActionBarPrimitive.ExportMarkdown
						render={
							<ActionBarMorePrimitive.Item className="aui-action-bar-more-item hover:bg-accent hover:text-accent-foreground focus:bg-accent focus:text-accent-foreground flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm outline-none select-none" />
						}
					>
						<DownloadIcon className="size-4" />
						Export as Markdown
					</ActionBarPrimitive.ExportMarkdown>
				</ActionBarMorePrimitive.Content>
			</ActionBarMorePrimitive.Root>
		</ActionBarPrimitive.Root>
	);
};

const UserMessage: FC = () => {
	return (
		<MessagePrimitive.Root
			data-slot="aui_user-message-root"
			className="fade-in slide-in-from-bottom-1 animate-in grid auto-rows-auto grid-cols-[minmax(72px,1fr)_auto] content-start gap-y-2 px-2 duration-150 [contain-intrinsic-size:auto_60px] [content-visibility:auto] [&:where(>*)]:col-start-2"
			data-role="user"
		>
			<UserMessageAttachments />

			<div className="col-start-2">
				<MessagePrimitive.Quote>
					{(quote) => <QuoteBlock {...quote} />}
				</MessagePrimitive.Quote>
			</div>

			<div className="group/user-bubble aui-user-message-content-wrapper relative col-start-2 min-w-0">
				<div className="aui-user-message-content peer bg-muted text-foreground rounded-xl px-4 py-2 wrap-break-word empty:hidden">
					<MessagePrimitive.Parts />
				</div>
				<div className="aui-user-action-bar-wrapper absolute start-0 top-1/2 -translate-x-full -translate-y-1/2 pe-2 peer-empty:hidden rtl:translate-x-full">
					<UserActionBar />
				</div>
				<div className="absolute end-1 -bottom-3 peer-empty:hidden">
					<UserCopyBar />
				</div>
			</div>

			<BranchPicker
				data-slot="aui_user-branch-picker"
				className="col-span-full col-start-1 row-start-3 -me-1 justify-end"
			/>
		</MessagePrimitive.Root>
	);
};

const UserActionBar: FC = () => {
	return (
		<ActionBarPrimitive.Root
			hideWhenRunning
			autohide="not-last"
			className="aui-user-action-bar-root flex flex-col items-end"
		>
			<ActionBarPrimitive.Edit
				render={
					<TooltipIconButton tooltip="Edit" className="aui-user-action-edit" />
				}
			>
				<PencilIcon />
			</ActionBarPrimitive.Edit>
		</ActionBarPrimitive.Root>
	);
};

// Copy-whole-question button, pinned to the bottom-right of the user bubble and
// revealed on hover. ActionBarPrimitive.Copy copies the full message text.
const UserCopyBar: FC = () => {
	return (
		<ActionBarPrimitive.Root
			autohide="always"
			className="aui-user-copy-bar-root text-muted-foreground animate-in fade-in duration-150"
		>
			<ActionBarPrimitive.Copy
				render={
					<TooltipIconButton
						tooltip="Copy"
						className="bg-background/80 size-7 rounded-full border shadow-sm backdrop-blur-sm"
					/>
				}
			>
				<AuiIf condition={(s) => s.message.isCopied}>
					<CheckIcon className="animate-in zoom-in-50 fade-in duration-200 ease-out" />
				</AuiIf>
				<AuiIf condition={(s) => !s.message.isCopied}>
					<CopyIcon className="animate-in zoom-in-75 fade-in duration-150" />
				</AuiIf>
			</ActionBarPrimitive.Copy>
		</ActionBarPrimitive.Root>
	);
};

const EditComposer: FC = () => {
	return (
		<MessagePrimitive.Root
			data-slot="aui_edit-composer-wrapper"
			className="flex flex-col px-2"
		>
			<ComposerPrimitive.Root className="aui-edit-composer-root border-border/60 dark:border-muted-foreground/15 ms-auto flex w-full max-w-[85%] flex-col rounded-(--composer-radius) border bg-(--composer-bg) shadow-[0_4px_16px_-8px_rgba(0,0,0,0.08),0_1px_2px_rgba(0,0,0,0.04)] dark:shadow-none">
				<ComposerPrimitive.Input
					className="aui-edit-composer-input text-foreground min-h-14 w-full resize-none bg-transparent px-4 pt-3 pb-1 text-base outline-none"
					autoFocus
				/>
				<div className="aui-edit-composer-footer mx-2.5 mb-2.5 flex items-center gap-1.5 self-end">
					<ComposerPrimitive.Cancel
						render={
							<Button
								variant="ghost"
								size="sm"
								className="h-8 rounded-full px-3.5"
							/>
						}
					>
						Cancel
					</ComposerPrimitive.Cancel>
					<ComposerPrimitive.Send
						render={<Button size="sm" className="h-8 rounded-full px-3.5" />}
					>
						Update
					</ComposerPrimitive.Send>
				</div>
			</ComposerPrimitive.Root>
		</MessagePrimitive.Root>
	);
};

const BranchPicker: FC<BranchPickerPrimitive.Root.Props> = ({
	className,
	...rest
}) => {
	return (
		<BranchPickerPrimitive.Root
			hideWhenSingleBranch
			className={cn(
				// Branch navigation is deferred (flat external-store can't model branches
				// without backend checkpoint support), so hide the picker — regenerate
				// replaces in place rather than branching. Re-enable when branching lands.
				"aui-branch-picker-root text-muted-foreground -ms-2 me-2 hidden items-center text-xs",
				className,
			)}
			{...rest}
		>
			<BranchPickerPrimitive.Previous
				render={<TooltipIconButton tooltip="Previous" />}
			>
				<ChevronLeftIcon />
			</BranchPickerPrimitive.Previous>
			<span className="aui-branch-picker-state font-medium">
				<BranchPickerPrimitive.Number /> / <BranchPickerPrimitive.Count />
			</span>
			<BranchPickerPrimitive.Next render={<TooltipIconButton tooltip="Next" />}>
				<ChevronRightIcon />
			</BranchPickerPrimitive.Next>
		</BranchPickerPrimitive.Root>
	);
};
