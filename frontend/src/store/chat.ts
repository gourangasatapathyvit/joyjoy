import { create } from "zustand";
import { persistPref } from "@/api/prefs";
import { sessionApi } from "@/api/sessions";
import type { ReasoningEffort, Source, TokenUsage } from "@/api/types";
import { STORAGE_KEYS, WORKSPACE_DOCK } from "@/lib/constants";
import { prefixedId } from "@/lib/utils";

const newThreadId = () => prefixedId("t");

// Persisted UI state (webui parity): the workspace dock's open/closed flag and
// the ACTIVE thread/session — so the last conversation (and therefore its
// workspace) is restored across screen navigation and full reloads.
const WS_KEY = STORAGE_KEYS.workspaceOpen;
const WS_WIDTH_KEY = STORAGE_KEYS.workspaceWidth;
const CONV_KEY = STORAGE_KEYS.conversationsOpen;
const TID_KEY = STORAGE_KEYS.activeThread;

const readWorkspaceOpen = (): boolean => {
	try {
		return localStorage.getItem(WS_KEY) === "1";
	} catch {
		return false;
	}
};

// The conversation sidebar defaults to OPEN; only an explicit "0" collapses it.
const readConversationsOpen = (): boolean => {
	try {
		return localStorage.getItem(CONV_KEY) !== "0";
	} catch {
		return true;
	}
};

const clampWidth = (w: number) =>
	Math.min(WORKSPACE_DOCK.maxWidth, Math.max(WORKSPACE_DOCK.minWidth, w));

const readWorkspaceWidth = (): number => {
	try {
		const v = Number(localStorage.getItem(WS_WIDTH_KEY));
		if (Number.isFinite(v) && v > 0) return clampWidth(v);
	} catch {
		// fall through to the default
	}
	return WORKSPACE_DOCK.defaultWidth;
};

const persistThreadId = (id: string) => {
	try {
		localStorage.setItem(TID_KEY, id);
	} catch {
		// localStorage unavailable — keep in-memory only
	}
};

// Set true only when we had to MINT a brand-new thread id (no persisted one) —
// i.e. a first-ever/empty chat with nothing to load. A restored id (refresh,
// settings→chat) is treated as an existing thread so its load shows the spinner.
let initialThreadFresh = false;

const readThreadId = (): string => {
	try {
		const v = localStorage.getItem(TID_KEY);
		if (v) return v;
	} catch {
		// fall through to a fresh id
	}
	const id = newThreadId();
	persistThreadId(id);
	initialThreadFresh = true;
	return id;
};

// UI selection state shared between the pickers/sidebar and the chat runtime,
// which reads the current values at send time via getState(). `threadId` is the
// active conversation; the runtime loads its messages when it changes and the
// workspace dock shows that session's files.
interface ChatState {
	model: string;
	reasoningEffort: ReasoningEffort;
	threadId: string;
	// True for a brand-new, never-sent chat (nothing to fetch → show the Welcome,
	// not a loading spinner). False for any thread that may have saved messages
	// (selected from the sidebar, restored on refresh, or returned-to from Settings).
	freshThread: boolean;
	workspaceOpen: boolean;
	// Left conversation sidebar open/collapsed (persisted). Collapsing lets the
	// chat reflow to full width.
	conversationsOpen: boolean;
	// Width of the right-hand workspace dock (px), drag-resizable + persisted.
	workspaceWidth: number;
	// When on, gated tool calls in the ACTIVE chat are approved automatically (no
	// HITL card). This is the operative per-thread value: it's persisted on the
	// session (DB) and re-hydrated per conversation by AutoApproveSync; new chats
	// inherit `autoApproveDefault`.
	autoApprove: boolean;
	// Account-level default for new chats (UserConfig.auto_approve_default).
	autoApproveDefault: boolean;
	// Live per-turn telemetry from the run SSE stream: latest token usage (drives
	// the Context Display badge) and citations for the most recent answer (Sources
	// footer). Reset when the active thread changes.
	usage: TokenUsage | null;
	// Citations keyed by assistant message id, so each turn keeps its own Sources
	// footer (live id during a run; backend message id after reload).
	sourcesByMessage: Record<string, Source[]>;
	// Bumped once each time a run completes successfully — drives a brief
	// "success" dot-matrix flash near the composer (the per-message status can't,
	// since the streaming message remounts as already-complete).
	successTick: number;
	setUsage: (usage: TokenUsage | null) => void;
	setSourcesForMessage: (messageId: string, sources: Source[]) => void;
	setSourcesMap: (map: Record<string, Source[]>) => void;
	bumpSuccess: () => void;
	setModel: (model: string) => void;
	setReasoningEffort: (effort: ReasoningEffort) => void;
	// User-driven toggle: reflect immediately AND persist on the current session.
	setAutoApprove: (on: boolean) => void;
	// In-memory only — used by AutoApproveSync to reflect a thread's stored value
	// (or the account default) without echoing a write back.
	hydrateAutoApprove: (on: boolean) => void;
	setAutoApproveDefault: (on: boolean) => void;
	setWorkspaceWidth: (px: number) => void;
	selectThread: (threadId: string) => void;
	newChat: () => void;
	toggleWorkspace: () => void;
	toggleConversations: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
	model: "gpt-5",
	reasoningEffort: "off",
	threadId: readThreadId(),
	freshThread: initialThreadFresh,
	workspaceOpen: readWorkspaceOpen(),
	conversationsOpen: readConversationsOpen(),
	workspaceWidth: readWorkspaceWidth(),
	autoApprove: false,
	autoApproveDefault: false,
	usage: null,
	sourcesByMessage: {},
	successTick: 0,
	setUsage: (usage) => set({ usage }),
	setSourcesForMessage: (messageId, sources) =>
		set((s) => ({
			sourcesByMessage: { ...s.sourcesByMessage, [messageId]: sources },
		})),
	setSourcesMap: (sourcesByMessage) => set({ sourcesByMessage }),
	bumpSuccess: () => set((s) => ({ successTick: s.successTick + 1 })),
	// The picker's choice is remembered as the user's default (server-persisted).
	setModel: (model) => {
		set({ model });
		persistPref({ default_model: model });
	},
	setReasoningEffort: (reasoningEffort) => {
		set({ reasoningEffort });
		persistPref({ default_reasoning: reasoningEffort });
	},
	setAutoApprove: (autoApprove) => {
		set({ autoApprove });
		// Persist on the active session so reopening the chat remembers it. Harmless
		// best-effort for a brand-new thread with no row yet — the next run persists
		// it via record_session anyway.
		sessionApi
			.setAutoApprove(useChatStore.getState().threadId, autoApprove)
			.catch(() => {});
	},
	hydrateAutoApprove: (autoApprove) => set({ autoApprove }),
	setAutoApproveDefault: (autoApproveDefault) => {
		set({ autoApproveDefault });
		persistPref({ auto_approve_default: autoApproveDefault });
	},
	// AutoApproveSync re-hydrates `autoApprove` for the opened thread; selecting or
	// starting a chat just switches the active thread id.
	selectThread: (threadId) => {
		persistThreadId(threadId);
		set({ threadId, freshThread: false, usage: null, sourcesByMessage: {} });
	},
	newChat: () => {
		const threadId = newThreadId();
		persistThreadId(threadId);
		// A brand-new chat starts from the account default until a run persists it.
		set({
			threadId,
			freshThread: true,
			autoApprove: useChatStore.getState().autoApproveDefault,
			usage: null,
			sourcesByMessage: {},
		});
	},
	setWorkspaceWidth: (px) => {
		const workspaceWidth = clampWidth(px);
		set({ workspaceWidth });
		try {
			localStorage.setItem(WS_WIDTH_KEY, String(workspaceWidth));
		} catch {
			// localStorage unavailable — keep in-memory only
		}
	},
	toggleWorkspace: () =>
		set((s) => {
			const workspaceOpen = !s.workspaceOpen;
			try {
				localStorage.setItem(WS_KEY, workspaceOpen ? "1" : "0");
			} catch {
				// localStorage unavailable — keep in-memory only
			}
			return { workspaceOpen };
		}),
	toggleConversations: () =>
		set((s) => {
			const conversationsOpen = !s.conversationsOpen;
			try {
				localStorage.setItem(CONV_KEY, conversationsOpen ? "1" : "0");
			} catch {
				// localStorage unavailable — keep in-memory only
			}
			return { conversationsOpen };
		}),
}));
