import { Thread } from "@/components/assistant-ui/thread";
import { ConversationSidebar } from "@/components/chat/ConversationSidebar";
import { ModelPicker } from "@/components/chat/ModelPicker";
import { JoyjoyRuntimeProvider } from "@/runtime/JoyjoyRuntimeProvider";

export function ChatPage() {
	return (
		<div className="flex min-h-0 flex-1">
			<ConversationSidebar />
			<JoyjoyRuntimeProvider>
				<div className="flex min-h-0 flex-1 flex-col">
					<div className="flex items-center justify-end border-b border-border px-4 py-2">
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
