import { create } from "zustand";
import type { ReasoningEffort } from "@/api/types";

const newThreadId = () => `t-${crypto.randomUUID()}`;

// UI selection state shared between the pickers/sidebar and the chat runtime,
// which reads the current values at send time via getState(). `threadId` is the
// active conversation; the runtime loads its messages when it changes.
interface ChatState {
	model: string;
	reasoningEffort: ReasoningEffort;
	threadId: string;
	setModel: (model: string) => void;
	setReasoningEffort: (effort: ReasoningEffort) => void;
	selectThread: (threadId: string) => void;
	newChat: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
	model: "gpt-5",
	reasoningEffort: "off",
	threadId: newThreadId(),
	setModel: (model) => set({ model }),
	setReasoningEffort: (reasoningEffort) => set({ reasoningEffort }),
	selectThread: (threadId) => set({ threadId }),
	newChat: () => set({ threadId: newThreadId() }),
}));
