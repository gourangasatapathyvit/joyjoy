import { create } from "zustand";
import { persistPref } from "@/api/prefs";
import type { ReasoningEffort } from "@/api/types";
import { STORAGE_KEYS } from "@/lib/constants";

const newThreadId = () => `t-${crypto.randomUUID()}`;

// Persisted UI state (webui parity): the workspace dock's open/closed flag and
// the ACTIVE thread/session — so the last conversation (and therefore its
// workspace) is restored across screen navigation and full reloads.
const WS_KEY = STORAGE_KEYS.workspaceOpen;
const TID_KEY = STORAGE_KEYS.activeThread;

const readWorkspaceOpen = (): boolean => {
	try {
		return localStorage.getItem(WS_KEY) === "1";
	} catch {
		return false;
	}
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
	setModel: (model: string) => void;
	setReasoningEffort: (effort: ReasoningEffort) => void;
	selectThread: (threadId: string) => void;
	newChat: () => void;
	toggleWorkspace: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
	model: "gpt-5",
	reasoningEffort: "off",
	threadId: readThreadId(),
	workspaceOpen: readWorkspaceOpen(),
	// The picker's choice is remembered as the user's default (server-persisted).
	setModel: (model) => {
		set({ model });
		persistPref({ default_model: model });
	},
	setReasoningEffort: (reasoningEffort) => {
		set({ reasoningEffort });
		persistPref({ default_reasoning: reasoningEffort });
	},
	selectThread: (threadId) => {
		persistThreadId(threadId);
		set({ threadId });
	},
	newChat: () => {
		const threadId = newThreadId();
		persistThreadId(threadId);
		set({ threadId });
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
