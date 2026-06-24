import { create } from "zustand";
import { persistPref } from "@/api/prefs";
import { sessionApi } from "@/api/sessions";
import type { ReasoningEffort } from "@/api/types";
import { STORAGE_KEYS, WORKSPACE_DOCK } from "@/lib/constants";

const newThreadId = () => `t-${crypto.randomUUID()}`;

// Persisted UI state (webui parity): the workspace dock's open/closed flag and
// the ACTIVE thread/session — so the last conversation (and therefore its
// workspace) is restored across screen navigation and full reloads.
const WS_KEY = STORAGE_KEYS.workspaceOpen;
const WS_WIDTH_KEY = STORAGE_KEYS.workspaceWidth;
const TID_KEY = STORAGE_KEYS.activeThread;

const readWorkspaceOpen = (): boolean => {
	try {
		return localStorage.getItem(WS_KEY) === "1";
	} catch {
		return false;
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

const readThreadId = (): string => {
	try {
		const v = localStorage.getItem(TID_KEY);
		if (v) return v;
	} catch {
		// fall through to a fresh id
	}
	const id = newThreadId();
	persistThreadId(id);
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
	workspaceOpen: boolean;
	// Width of the right-hand workspace dock (px), drag-resizable + persisted.
	workspaceWidth: number;
	// When on, gated tool calls in the ACTIVE chat are approved automatically (no
	// HITL card). This is the operative per-thread value: it's persisted on the
	// session (DB) and re-hydrated per conversation by AutoApproveSync; new chats
	// inherit `autoApproveDefault`.
	autoApprove: boolean;
	// Account-level default for new chats (UserConfig.auto_approve_default).
	autoApproveDefault: boolean;
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
}

export const useChatStore = create<ChatState>((set) => ({
	model: "gpt-5",
	reasoningEffort: "off",
	threadId: readThreadId(),
	workspaceOpen: readWorkspaceOpen(),
	workspaceWidth: readWorkspaceWidth(),
	autoApprove: false,
	autoApproveDefault: false,
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
		set({ threadId });
	},
	newChat: () => {
		const threadId = newThreadId();
		persistThreadId(threadId);
		// A brand-new chat starts from the account default until a run persists it.
		set({ threadId, autoApprove: useChatStore.getState().autoApproveDefault });
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
}));
