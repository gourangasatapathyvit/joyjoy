import { create } from "zustand";
import type { ReasoningEffort } from "@/api/types";

const newThreadId = () => `t-${crypto.randomUUID()}`;

// Persist the workspace dock's open/closed state (webui parity — it keeps the
// panel state in localStorage too).
const WS_KEY = "joyjoy-workspace-open";
const readWorkspaceOpen = (): boolean => {
	try {
		return localStorage.getItem(WS_KEY) === "1";
	} catch {
		return false;
	}
};

// UI selection state shared between the pickers/sidebar and the chat runtime,
// which reads the current values at send time via getState(). `threadId` is the
// active conversation; the runtime loads its messages when it changes.
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
	threadId: newThreadId(),
	workspaceOpen: readWorkspaceOpen(),
	setModel: (model) => set({ model }),
	setReasoningEffort: (reasoningEffort) => set({ reasoningEffort }),
	selectThread: (threadId) => set({ threadId }),
	newChat: () => set({ threadId: newThreadId() }),
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
