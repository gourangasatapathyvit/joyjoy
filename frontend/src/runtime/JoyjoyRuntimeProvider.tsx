import {
	type AppendMessage,
	AssistantRuntimeProvider,
	type QuoteInfo,
	type ThreadMessageLike,
	useExternalStoreRuntime,
} from "@assistant-ui/react";
import { useQueryClient } from "@tanstack/react-query";
import {
	createContext,
	type ReactNode,
	useCallback,
	useContext,
	useEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import {
	cancelRun,
	createRun,
	respondApproval,
	runEventsUrl,
} from "@/api/client";
import { sessionApi } from "@/api/sessions";
import type { MediaItem, RunEvent, SessionMessageWire } from "@/api/types";
import {
	isMediaFile,
	mediaUrl,
	mimeOf,
	splitMediaMarkers,
	workspaceRawUrl,
} from "@/lib/media";
import { baseName } from "@/lib/text";
import { useChatStore } from "@/store/chat";

type JsonValue =
	| string
	| number
	| boolean
	| null
	| JsonValue[]
	| { [key: string]: JsonValue };
type JsonObject = { [key: string]: JsonValue };

// Internal message model; converted to assistant-ui's ThreadMessageLike on render.
type UIPart =
	| { type: "text"; text: string }
	| { type: "reasoning"; text: string }
	| {
			type: "tool-call";
			toolCallId: string;
			toolName: string;
			args: JsonObject;
			argsText: string;
			result?: string;
			isError?: boolean;
			media?: MediaItem[];
	  };

// All agent media is emitted as an assistant-ui `file` part — its `data` may be
// any URL (assistant-ui's `image` part rejects non-https/data URLs, but our media
// is served from a relative /v1 proxy path). MediaFile renders image mimes inline.
type AuiMediaPart = {
	type: "file";
	data: string;
	mimeType: string;
	filename?: string;
};

// The full set of content parts convertMessage emits (annotating flatMap's return
// so TS infers the union across all branches, not just the first).
type AuiPart =
	| { type: "text"; text: string }
	| { type: "reasoning"; text: string }
	| {
			type: "tool-call";
			toolCallId: string;
			toolName: string;
			args: JsonObject;
			argsText: string;
			result?: string;
			status?: { type: "running" };
	  }
	| AuiMediaPart;

// Build a media part from a URL (a MEDIA: marker or a workspace file path).
function urlMediaPart(url: string, filename: string): AuiMediaPart {
	return { type: "file", data: url, mimeType: mimeOf(filename), filename };
}
// Build a media part from a backend base64 block (deepagents read_file binary).
function blockMediaPart(md: MediaItem): AuiMediaPart {
	return {
		type: "file",
		data: md.data_url,
		mimeType: md.mime_type,
		filename: md.filename ?? undefined,
	};
}

interface UIMessage {
	id: string;
	role: "user" | "assistant";
	parts: UIPart[];
	createdAt: number;
	// Set on user messages created from a "Quote" selection — rendered as a
	// quote block above the bubble and prepended to the text sent to the agent.
	quote?: QuoteInfo;
}

// Tracks the in-flight run so onCancel can stop it.
interface ActiveRun {
	assistantId: string;
	runId: string | null;
	es: EventSource | null;
	finish: () => void;
}

// ── HITL approval context ──────────────────────────────────────────────────
// External-store doesn't honor a manually-set `requires-action` tool status, so
// we surface the pending approval (keyed by toolCallId) through context and the
// ToolFallback renders Allow/Deny inline, attached to the tool call it gates.
interface ApprovalInfo {
	approvalId: string;
	runId: string;
}
interface ApprovalsContextValue {
	pending: Record<string, ApprovalInfo>;
	hasPending: boolean;
	respond: (toolCallId: string, decision: "approve" | "reject") => void;
}
const ApprovalsContext = createContext<ApprovalsContextValue>({
	pending: {},
	hasPending: false,
	respond: () => {},
});
export const useApprovals = (): ApprovalsContextValue =>
	useContext(ApprovalsContext);

const newId = (prefix: string): string => `${prefix}-${crypto.randomUUID()}`;
const textOf = (m: UIMessage): string =>
	m.parts
		.map((p) => (p.type === "text" ? p.text : ""))
		.join("")
		.trim();

// The Python agent has no notion of assistant-ui's JS quote injection, so we
// fold a quoted selection into the prompt as a markdown blockquote ahead of the
// user's text — the agent then sees exactly what the user was replying to.
const buildSendText = (text: string, quote?: QuoteInfo): string => {
	const q = quote?.text.trim();
	if (!q) return text;
	const block = q
		.split("\n")
		.map((line) => `> ${line}`)
		.join("\n");
	return `${block}\n\n${text}`;
};

// Rebuild a saved thread (GET /v1/sessions/{tid}/messages) into UI messages,
// re-attaching each ToolMessage's output to the AI tool-call it answers.
function wireToUI(wire: SessionMessageWire[]): UIMessage[] {
	const out: UIMessage[] = [];
	const toolLoc = new Map<string, { mi: number; pi: number }>();
	for (const m of wire) {
		if (m.role === "user") {
			out.push({
				id: newId("u"),
				role: "user",
				parts: [{ type: "text", text: m.content }],
				createdAt: Date.now(),
			});
		} else if (m.role === "assistant") {
			const parts: UIPart[] = [];
			if (m.content) parts.push({ type: "text", text: m.content });
			for (const tc of m.tool_calls ?? []) {
				toolLoc.set(tc.id, { mi: out.length, pi: parts.length });
				parts.push({
					type: "tool-call",
					toolCallId: tc.id,
					toolName: tc.name,
					args: (tc.args as JsonObject) ?? {},
					argsText: JSON.stringify(tc.args ?? {}, null, 2),
				});
			}
			if (parts.length)
				out.push({
					id: newId("a"),
					role: "assistant",
					parts,
					createdAt: Date.now(),
				});
		} else if (m.role === "tool" && m.tool_call_id) {
			const loc = toolLoc.get(m.tool_call_id);
			const part = loc ? out[loc.mi]?.parts[loc.pi] : undefined;
			if (part?.type === "tool-call") {
				part.result = m.content;
				if (m.media?.length) part.media = m.media;
			}
		}
	}
	return out;
}

export function JoyjoyRuntimeProvider({ children }: { children: ReactNode }) {
	const [messages, setMessages] = useState<UIMessage[]>([]);
	const [isRunning, setIsRunning] = useState(false);
	const [pending, setPending] = useState<Record<string, ApprovalInfo>>({});
	const threadId = useChatStore((s) => s.threadId);
	const queryClient = useQueryClient();
	const loadSeqRef = useRef(0);
	const messagesRef = useRef<UIMessage[]>(messages);
	messagesRef.current = messages;
	const activeRunRef = useRef<ActiveRun | null>(null);
	// toolName → most recent toolCallId from tool.started, to correlate the
	// backend's approval.request (which carries no toolCallId) to its tool call.
	const toolByNameRef = useRef<Record<string, string>>({});

	const patch = useCallback((id: string, fn: (m: UIMessage) => UIMessage) => {
		setMessages((prev) => prev.map((m) => (m.id === id ? fn(m) : m)));
	}, []);

	const respond = useCallback(
		(toolCallId: string, decision: "approve" | "reject") => {
			setPending((prev) => {
				const info = prev[toolCallId];
				if (info)
					respondApproval(info.runId, info.approvalId, decision).catch(
						() => {},
					);
				const next = { ...prev };
				delete next[toolCallId];
				return next;
			});
		},
		[],
	);

	// When auto-approve flips on (composer toggle or the in-card button) while
	// approvals are already waiting, clear them too so the user never has to tap.
	const autoApprove = useChatStore((s) => s.autoApprove);
	useEffect(() => {
		if (!autoApprove) return;
		for (const tcid of Object.keys(pending)) respond(tcid, "approve");
	}, [autoApprove, pending, respond]);

	// Drive one assistant turn: stream the run into the placeholder `assistantId`.
	// Returns a promise that resolves when the stream ends (per the ExternalStore
	// contract — onNew/onReload await it; isRunning is managed manually around it).
	const runTurn = useCallback(
		(assistantId: string, text: string): Promise<void> => {
			setIsRunning(true);
			const {
				model,
				reasoningEffort,
				threadId: activeThreadId,
				autoApprove,
			} = useChatStore.getState();

			const appendText = (delta: string) =>
				patch(assistantId, (m) => {
					const parts = [...m.parts];
					const last = parts[parts.length - 1];
					if (last?.type === "text")
						parts[parts.length - 1] = { type: "text", text: last.text + delta };
					else parts.push({ type: "text", text: delta });
					return { ...m, parts };
				});

			const appendReasoning = (delta: string) =>
				patch(assistantId, (m) => {
					const parts = [...m.parts];
					const idx = parts.findIndex((p) => p.type === "reasoning");
					if (idx >= 0) {
						const r = parts[idx] as Extract<UIPart, { type: "reasoning" }>;
						parts[idx] = { type: "reasoning", text: r.text + delta };
					} else {
						parts.unshift({ type: "reasoning", text: delta });
					}
					return { ...m, parts };
				});

			const startTool = (ev: Extract<RunEvent, { event: "tool.started" }>) => {
				const id = ev.toolCallId ?? newId("tc");
				const name = ev.tool ?? ev.name ?? "tool";
				toolByNameRef.current[name] = id; // sync, before approval.request can read it
				patch(assistantId, (m) => {
					if (
						m.parts.some((p) => p.type === "tool-call" && p.toolCallId === id)
					)
						return m;
					return {
						...m,
						parts: [
							...m.parts,
							{
								type: "tool-call",
								toolCallId: id,
								toolName: name,
								args: (ev.args as JsonObject) ?? {},
								argsText: JSON.stringify(ev.args ?? {}, null, 2),
							},
						],
					};
				});
			};

			const completeTool = (
				ev: Extract<RunEvent, { event: "tool.completed" }>,
			) => {
				const tcid = ev.toolCallId;
				if (tcid) {
					setPending((prev) => {
						if (!prev[tcid]) return prev;
						const next = { ...prev };
						delete next[tcid];
						return next;
					});
				}
				patch(assistantId, (m) => ({
					...m,
					parts: m.parts.map((p) =>
						p.type === "tool-call" && p.toolCallId === ev.toolCallId
							? {
									...p,
									result: ev.result ?? "",
									isError: Boolean(ev.is_error),
									media: ev.media,
								}
							: p,
					),
				}));
			};

			const requestApproval = (
				ev: Extract<RunEvent, { event: "approval.request" }>,
			) => {
				const name = ev.tool ?? ev.name ?? "tool";
				// Auto-approve mode (per-chat): resolve the gate immediately without
				// ever surfacing a card. The tool still streams its started/completed
				// events, so the call remains visible in the transcript.
				if (useChatStore.getState().autoApprove) {
					respondApproval(ev.run_id, ev.approval_id, "approve").catch(() => {});
					return;
				}
				let toolCallId = toolByNameRef.current[name];
				if (!toolCallId) {
					toolCallId = newId("tc");
					const tcid = toolCallId;
					patch(assistantId, (m) => ({
						...m,
						parts: [
							...m.parts,
							{
								type: "tool-call",
								toolCallId: tcid,
								toolName: name,
								args: (ev.args as JsonObject) ?? {},
								argsText: JSON.stringify(ev.args ?? {}, null, 2),
							},
						],
					}));
				}
				const tcid = toolCallId;
				setPending((prev) => ({
					...prev,
					[tcid]: { approvalId: ev.approval_id, runId: ev.run_id },
				}));
			};

			return new Promise<void>((resolve) => {
				let settled = false;
				const finish = () => {
					if (settled) return;
					settled = true;
					setIsRunning(false);
					// A run may have created/renamed the session — refresh the sidebar.
					queryClient.invalidateQueries({ queryKey: ["sessions"] });
					if (activeRunRef.current?.assistantId === assistantId)
						activeRunRef.current = null;
					resolve();
				};
				const handle: ActiveRun = {
					assistantId,
					runId: null,
					es: null,
					finish,
				};
				activeRunRef.current = handle;

				createRun({
					input: text,
					model,
					reasoning_effort:
						reasoningEffort === "off" ? undefined : reasoningEffort,
					thread_id: activeThreadId,
					auto_approve: autoApprove,
				})
					.then(({ run_id }) => {
						handle.runId = run_id;
						const es = new EventSource(runEventsUrl(run_id));
						handle.es = es;
						es.onmessage = (e) => {
							if (e.data === "[DONE]") {
								es.close();
								finish();
								return;
							}
							let ev: RunEvent;
							try {
								ev = JSON.parse(e.data) as RunEvent;
							} catch {
								return;
							}
							switch (ev.event) {
								case "message.delta":
									appendText(ev.delta);
									break;
								case "reasoning.available":
									appendReasoning(ev.delta ?? ev.text);
									break;
								case "tool.started":
									startTool(ev);
									break;
								case "tool.completed":
									completeTool(ev);
									break;
								case "approval.request":
									requestApproval(ev);
									break;
								case "run.completed":
									es.close();
									finish();
									break;
								case "run.failed":
									appendText(`\n\n_[error: ${ev.error ?? "run failed"}]_`);
									es.close();
									finish();
									break;
								case "run.cancelled":
									es.close();
									finish();
									break;
							}
						};
						es.onerror = () => {
							es.close();
							finish();
						};
					})
					.catch((err: unknown) => {
						appendText(`\n\n_[error: ${String(err)}]_`);
						finish();
					});
			});
		},
		[patch, queryClient],
	);

	const onNew = useCallback(
		async (message: AppendMessage) => {
			const text = message.content
				.map((c) => (c.type === "text" ? c.text : ""))
				.join("")
				.trim();
			if (!text) return;
			// The composer attaches a "Quote" selection at metadata.custom.quote
			// (see assistant-ui's base composer send()).
			const quote = (
				message.metadata?.custom as { quote?: QuoteInfo } | undefined
			)?.quote;
			const assistantId = newId("a");
			setMessages((prev) => [
				...prev,
				{
					id: newId("u"),
					role: "user",
					parts: [{ type: "text", text }],
					createdAt: Date.now(),
					...(quote ? { quote } : {}),
				},
				{
					id: assistantId,
					role: "assistant",
					parts: [],
					createdAt: Date.now(),
				},
			]);
			await runTurn(assistantId, buildSendText(text, quote));
		},
		[runTurn],
	);

	// Regenerate the latest turn: drop the last assistant response and re-run the
	// last user message. (Older-message regenerate + true checkpoint replace need
	// backend support — deferred; this covers the common "redo the last answer".)
	const onReload = useCallback(async () => {
		const msgs = messagesRef.current;
		let userIdx = -1;
		for (let i = msgs.length - 1; i >= 0; i--) {
			if (msgs[i].role === "user") {
				userIdx = i;
				break;
			}
		}
		if (userIdx < 0) return;
		const text = textOf(msgs[userIdx]);
		if (!text) return;
		const quote = msgs[userIdx].quote;
		const assistantId = newId("a");
		setMessages((prev) => {
			let ui = -1;
			for (let i = prev.length - 1; i >= 0; i--) {
				if (prev[i].role === "user") {
					ui = i;
					break;
				}
			}
			const kept = ui >= 0 ? prev.slice(0, ui + 1) : prev;
			return [
				...kept,
				{
					id: assistantId,
					role: "assistant",
					parts: [],
					createdAt: Date.now(),
				},
			];
		});
		await runTurn(assistantId, buildSendText(text, quote));
	}, [runTurn]);

	// Edit a previous user message: replace it (and drop everything after its
	// parent) with the new text, then re-run. Wires the edit pencil on user
	// bubbles. Like onReload, the backend thread keeps the prior turns (true
	// checkpoint replace needs backend support — deferred); the agent answers the
	// edited message with the full thread context.
	const onEdit = useCallback(
		async (message: AppendMessage) => {
			const text = message.content
				.map((c) => (c.type === "text" ? c.text : ""))
				.join("")
				.trim();
			if (!text) return;
			const quote = (
				message.metadata?.custom as { quote?: QuoteInfo } | undefined
			)?.quote;
			const parentId = message.parentId;
			const assistantId = newId("a");
			setMessages((prev) => {
				// Keep up to and including the edited message's parent; the edited
				// user message + a fresh assistant placeholder replace the rest.
				const cut = parentId ? prev.findIndex((m) => m.id === parentId) : -1;
				const kept = cut >= 0 ? prev.slice(0, cut + 1) : [];
				return [
					...kept,
					{
						id: newId("u"),
						role: "user",
						parts: [{ type: "text", text }],
						createdAt: Date.now(),
						...(quote ? { quote } : {}),
					},
					{
						id: assistantId,
						role: "assistant",
						parts: [],
						createdAt: Date.now(),
					},
				];
			});
			await runTurn(assistantId, buildSendText(text, quote));
		},
		[runTurn],
	);

	// Stop the in-flight run (wires the composer's "Stop generating" button).
	const onCancel = useCallback(async () => {
		const h = activeRunRef.current;
		if (!h) return;
		h.es?.close();
		if (h.runId) cancelRun(h.runId).catch(() => {});
		h.finish();
	}, []);

	// Load a saved conversation when the active thread changes (sidebar select or
	// "new chat"). A brand-new thread isn't persisted yet → 404 → render empty.
	// loadSeqRef guards against an older fetch resolving after a newer switch.
	const loadThread = useCallback(async (tid: string) => {
		const seq = ++loadSeqRef.current;
		activeRunRef.current?.es?.close();
		activeRunRef.current?.finish();
		setPending({});
		toolByNameRef.current = {};
		try {
			const { messages: wire } = await sessionApi.messages(tid);
			if (seq === loadSeqRef.current) setMessages(wireToUI(wire));
		} catch {
			if (seq === loadSeqRef.current) setMessages([]);
		}
	}, []);

	useEffect(() => {
		loadThread(threadId);
	}, [threadId, loadThread]);

	const convertMessage = useCallback(
		(m: UIMessage): ThreadMessageLike => ({
			id: m.id,
			role: m.role,
			createdAt: new Date(m.createdAt),
			// Surfaces the quote block above the user bubble (useMessageQuote reads
			// metadata.custom.quote).
			...(m.quote ? { metadata: { custom: { quote: m.quote } } } : {}),
			content: m.parts
				.filter(
					(p, i, arr) =>
						p.type !== "tool-call" ||
						arr.findIndex(
							(q) => q.type === "tool-call" && q.toolCallId === p.toolCallId,
						) === i,
				)
				.flatMap((p): AuiPart[] => {
					// Text → text, lifting any `MEDIA:<path>` lines into media parts.
					if (p.type === "text")
						return splitMediaMarkers(p.text).map((seg) =>
							seg.kind === "text"
								? { type: "text" as const, text: seg.text }
								: urlMediaPart(mediaUrl(seg.path), baseName(seg.path)),
						);
					if (p.type === "reasoning")
						return [{ type: "reasoning" as const, text: p.text }];
					// Tool call, plus media it produced (write_file → workspace file) or
					// returned (read_file → base64 blocks).
					const base = {
						type: "tool-call" as const,
						toolCallId: p.toolCallId,
						toolName: p.toolName,
						args: p.args,
						argsText: p.argsText,
						result: p.result,
					};
					const extras: AuiMediaPart[] = [];
					const fp = p.args?.file_path ?? p.args?.path;
					if (
						(p.toolName === "write_file" || p.toolName === "edit_file") &&
						typeof fp === "string" &&
						isMediaFile(fp)
					)
						extras.push(
							urlMediaPart(workspaceRawUrl(threadId, fp), baseName(fp)),
						);
					for (const md of p.media ?? []) extras.push(blockMediaPart(md));
					return [
						p.result !== undefined
							? base
							: { ...base, status: { type: "running" as const } },
						...extras,
					];
				}),
		}),
		[threadId],
	);

	const runtime = useExternalStoreRuntime({
		messages,
		isRunning,
		convertMessage,
		onNew,
		onEdit,
		onReload,
		onCancel,
	});
	const approvalsValue = useMemo<ApprovalsContextValue>(
		() => ({ pending, hasPending: Object.keys(pending).length > 0, respond }),
		[pending, respond],
	);

	return (
		<AssistantRuntimeProvider runtime={runtime}>
			<ApprovalsContext.Provider value={approvalsValue}>
				{children}
			</ApprovalsContext.Provider>
		</AssistantRuntimeProvider>
	);
}
