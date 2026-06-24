import {
	Check,
	Pencil,
	Pin,
	PinOff,
	Plus,
	Search,
	Trash2,
	X,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSessionMutations, useSessions } from "@/api/sessions";
import type { Session } from "@/api/types";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/store/chat";

// Conversation list for the chat view (webui sidebar style: 300px, gold-tinted
// active item, hover-reveal rename/delete/pin). Pinned conversations sort into a
// "Pinned" group at the top (per-user, persisted). Selecting a thread updates the
// shared store; the runtime loads that thread's messages in response.
export function ConversationSidebar() {
	const { t } = useTranslation();
	const { data, isLoading } = useSessions();
	const { rename, remove, setPinned } = useSessionMutations();
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
	const togglePin = (s: Session) =>
		setPinned.mutate({ tid: s.thread_id, pinned: !s.pinned });

	// Backend already sorts pinned-first; split so we can show a "Pinned" group.
	const pinned = sessions.filter((s) => s.pinned);
	const recent = sessions.filter((s) => !s.pinned);

	const renderItem = (s: Session) => {
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
							title={t("common.save")}
							className="text-muted-foreground hover:text-foreground"
						>
							<Check className="size-4" />
						</button>
						<button
							type="button"
							onClick={() => setEditing(null)}
							title={t("common.cancel")}
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
						{s.title || t("conversations.untitled")}
					</button>
					<button
						type="button"
						onClick={() => togglePin(s)}
						title={s.pinned ? t("conversations.unpin") : t("conversations.pin")}
						className={cn(
							"shrink-0 transition-opacity hover:text-primary",
							s.pinned
								? "text-primary opacity-100"
								: "opacity-0 group-hover:opacity-100",
						)}
					>
						{s.pinned ? (
							<PinOff className="size-3.5" />
						) : (
							<Pin className="size-3.5" />
						)}
					</button>
					<button
						type="button"
						onClick={() => startEdit(s.thread_id, s.title)}
						title={t("common.rename")}
						className="shrink-0 opacity-0 transition-opacity hover:text-primary group-hover:opacity-100"
					>
						<Pencil className="size-3.5" />
					</button>
					<button
						type="button"
						onClick={() => onDelete(s.thread_id)}
						title={t("common.delete")}
						className="shrink-0 opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
					>
						<Trash2 className="size-3.5" />
					</button>
				</div>
			</li>
		);
	};

	const groupCaption =
		"px-2 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground";

	return (
		<aside className="flex w-[300px] shrink-0 flex-col border-r border-border bg-sidebar">
			<div className="flex items-center justify-between px-4 py-3">
				<span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
					{t("conversations.heading")}
				</span>
				<button
					type="button"
					onClick={() => newChat()}
					title={t("conversations.newChat")}
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
					placeholder={t("conversations.searchPlaceholder")}
					className="w-full rounded-lg border border-border bg-background py-[7px] pr-8 pl-8 text-[13px] outline-none transition-[box-shadow,border-color] placeholder:text-muted-foreground focus:border-primary focus:ring-[3px] focus:ring-primary/15"
				/>
				{query && (
					<button
						type="button"
						onClick={() => setQuery("")}
						title={t("conversation.clear")}
						className="-translate-y-1/2 absolute top-1/2 right-[18px] inline-flex size-6 items-center justify-center rounded-md text-muted-foreground hover:text-foreground"
					>
						<X className="size-3.5" />
					</button>
				)}
			</div>

			<div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
				{isLoading ? (
					<p className="px-2 py-4 text-xs text-muted-foreground">
						{t("common.loading")}
					</p>
				) : sessions.length === 0 ? (
					<p className="px-2 py-4 text-xs leading-relaxed text-muted-foreground">
						{q ? t("common.noMatches") : t("conversations.empty")}
					</p>
				) : pinned.length === 0 ? (
					<ul className="flex flex-col gap-0.5">{sessions.map(renderItem)}</ul>
				) : (
					<>
						<p className={groupCaption}>
							<Pin className="mr-1 inline size-3 align-[-1px]" />
							{t("conversations.pinned")}
						</p>
						<ul className="flex flex-col gap-0.5">{pinned.map(renderItem)}</ul>
						{recent.length > 0 && (
							<>
								<p className={cn(groupCaption, "mt-1")}>
									{t("conversations.recent")}
								</p>
								<ul className="flex flex-col gap-0.5">
									{recent.map(renderItem)}
								</ul>
							</>
						)}
					</>
				)}
			</div>
		</aside>
	);
}
