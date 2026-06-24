import { PanelLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Thread } from "@/components/assistant-ui/thread";
import { ConversationSidebar } from "@/components/chat/ConversationSidebar";
import { ModelPicker } from "@/components/chat/ModelPicker";
import { JoyjoyRuntimeProvider } from "@/runtime/JoyjoyRuntimeProvider";
import { useChatStore } from "@/store/chat";

export function ChatPage() {
	const { t } = useTranslation();
	const conversationsOpen = useChatStore((s) => s.conversationsOpen);
	const toggleConversations = useChatStore((s) => s.toggleConversations);

	return (
		<div className="flex min-h-0 flex-1">
			{conversationsOpen && <ConversationSidebar />}
			<JoyjoyRuntimeProvider>
				{/* flex-1 → the chat reflows to full width when the sidebar collapses */}
				<div className="flex min-h-0 flex-1 flex-col">
					<div className="flex items-center justify-between border-b border-border px-4 py-2">
						{conversationsOpen ? (
							<span />
						) : (
							<button
								type="button"
								onClick={() => toggleConversations()}
								title={t("conversations.expand")}
								className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary"
							>
								<PanelLeft className="size-4" />
							</button>
						)}
						<ModelPicker />
					</div>
					<div className="min-h-0 flex-1">
						<Thread />
					</div>
				</div>
			</JoyjoyRuntimeProvider>
		</div>
	);
}
