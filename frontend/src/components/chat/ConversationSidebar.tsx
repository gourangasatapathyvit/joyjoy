import { Check, Pencil, Plus, Search, Trash2, X } from "lucide-react";
import { useState } from "react";
import { useSessionMutations, useSessions } from "@/api/sessions";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/store/chat";

// Conversation list for the chat view (webui sidebar style: 300px, gold-tinted
// active item, hover-reveal rename/delete). Selecting a thread updates the
// shared store; the runtime loads that thread's messages in response.
export function ConversationSidebar() {
	const { data, isLoading } = useSessions();
	const { rename, remove } = useSessionMutations();
	const threadId = useChatStore((s) => s.threadId);
	const selectThread = useChatStore((s) => s.selectThread);
	const newChat = useChatStore((s) => s.newChat);

	const [query, setQuery] = useState("");
	const [editing, setEditing] = useState<string | null>(null);
	const [draft, setDraft] = useState("");

	const all = data?.sessions ?? [];
	const q = query.trim().toLowerCase();
	const sessions = q
		? all.filter((s) => (s.title || "").toLowerCase().includes(q))
		: all;

	const startEdit = (tid: string, title: string) => {
		setEditing(tid);
		setDraft(title);
	};
	const commitEdit = (tid: string) => {
		const title = draft.trim();
		if (title) rename.mutate({ tid, title });
		setEditing(null);
	};
	const onDelete = (tid: string) => {
		remove.mutate(tid);
		if (tid === threadId) newChat();
	};

	return (
		<aside className="flex w-[300px] shrink-0 flex-col border-r border-border bg-sidebar">
			<div className="flex items-center justify-between px-4 py-3">
				<span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
					Conversations
				</span>
				<button
					type="button"
					onClick={() => newChat()}
					title="New chat"
					className="inline-flex size-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary"
				>
					<Plus className="size-4" />
				</button>
			</div>

			<div className="relative px-3 pb-2">
				<Search className="-translate-y-1/2 pointer-events-none absolute top-1/2 left-[22px] size-3.5 text-muted-foreground opacity-70" />
				<input
					value={query}
					onChange={(e) => setQuery(e.target.value)}
					placeholder="Search conversations"
					className="w-full rounded-lg border border-border bg-background py-[7px] pr-8 pl-8 text-[13px] outline-none transition-[box-shadow,border-color] placeholder:text-muted-foreground focus:border-primary focus:ring-[3px] focus:ring-primary/15"
				/>
				{query && (
					<button
						type="button"
						onClick={() => setQuery("")}
						title="Clear"
						className="-translate-y-1/2 absolute top-1/2 right-[18px] inline-flex size-6 items-center justify-center rounded-md text-muted-foreground hover:text-foreground"
					>
						<X className="size-3.5" />
					</button>
				)}
			</div>

			<div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
				{isLoading ? (
					<p className="px-2 py-4 text-xs text-muted-foreground">Loading…</p>
				) : sessions.length === 0 ? (
					<p className="px-2 py-4 text-xs leading-relaxed text-muted-foreground">
						{q
							? "No matches."
							: "No conversations yet. Start chatting to create one."}
					</p>
				) : (
					<ul className="flex flex-col gap-0.5">
						{sessions.map((s) => {
							const active = s.thread_id === threadId;
							if (editing === s.thread_id) {
								return (
									<li key={s.thread_id}>
										<div className="flex items-center gap-1 px-1 py-1">
											<input
												ref={(el) => el?.focus()}
												value={draft}
												onChange={(e) => setDraft(e.target.value)}
												onKeyDown={(e) => {
													if (e.key === "Enter") commitEdit(s.thread_id);
													if (e.key === "Escape") setEditing(null);
												}}
												className="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1 text-[13px] outline-none focus:border-primary focus:ring-[3px] focus:ring-primary/15"
											/>
											<button
												type="button"
												onClick={() => commitEdit(s.thread_id)}
												title="Save"
												className="text-muted-foreground hover:text-foreground"
											>
												<Check className="size-4" />
											</button>
											<button
												type="button"
												onClick={() => setEditing(null)}
												title="Cancel"
												className="text-muted-foreground hover:text-foreground"
											>
												<X className="size-4" />
											</button>
										</div>
									</li>
								);
							}
							return (
								<li key={s.thread_id}>
									<div
										className={cn(
											"group flex items-center gap-1 rounded-lg px-2 py-2 text-[13px] transition-colors",
											active
												? "bg-primary/10 text-primary"
												: "text-muted-foreground hover:bg-foreground/5 hover:text-foreground",
										)}
									>
										<button
											type="button"
											onClick={() => selectThread(s.thread_id)}
											className="min-w-0 flex-1 truncate text-left"
											title={s.title}
										>
											{s.title || "Untitled"}
										</button>
										<button
											type="button"
											onClick={() => startEdit(s.thread_id, s.title)}
											title="Rename"
											className="shrink-0 opacity-0 transition-opacity hover:text-primary group-hover:opacity-100"
										>
											<Pencil className="size-3.5" />
										</button>
										<button
											type="button"
											onClick={() => onDelete(s.thread_id)}
											title="Delete"
											className="shrink-0 opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
										>
											<Trash2 className="size-3.5" />
										</button>
									</div>
								</li>
							);
						})}
					</ul>
				)}
			</div>
		</aside>
	);
}
