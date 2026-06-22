import { useQueryClient } from "@tanstack/react-query";
import type { ChangeEvent } from "react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { sessionApi, useSessionMutations } from "@/api/sessions";
import { Button } from "@/components/ui/button";
import { useChatStore } from "@/store/chat";

function downloadFile(name: string, content: string, type: string) {
	const blob = new Blob([content], { type });
	const url = URL.createObjectURL(blob);
	const a = document.createElement("a");
	a.href = url;
	a.download = name;
	a.click();
	URL.revokeObjectURL(url);
}

// Conversation = transcript/JSON export, import, and clear of the active chat.
export function ConversationPane() {
	const { t } = useTranslation();
	const threadId = useChatStore((s) => s.threadId);
	const newChat = useChatStore((s) => s.newChat);
	const selectThread = useChatStore((s) => s.selectThread);
	const { remove } = useSessionMutations();
	const qc = useQueryClient();
	const fileRef = useRef<HTMLInputElement>(null);
	const [busy, setBusy] = useState(false);
	const [note, setNote] = useState<string | null>(null);

	const getMessages = async () =>
		(await sessionApi.messages(threadId)).messages ?? [];

	const onTranscript = async () => {
		setBusy(true);
		setNote(null);
		try {
			const m = await getMessages();
			const md = m.length
				? m.map((x) => `## ${x.role}\n\n${x.content || ""}`).join("\n\n")
				: "(empty conversation)";
			downloadFile(`transcript-${threadId}.md`, md, "text/markdown");
		} finally {
			setBusy(false);
		}
	};

	const onJson = async () => {
		setBusy(true);
		setNote(null);
		try {
			const m = await getMessages();
			downloadFile(
				`conversation-${threadId}.json`,
				JSON.stringify({ thread_id: threadId, messages: m }, null, 2),
				"application/json",
			);
		} finally {
			setBusy(false);
		}
	};

	const onImportFile = (e: ChangeEvent<HTMLInputElement>) => {
		const file = e.target.files?.[0];
		e.target.value = "";
		if (!file) return;
		const reader = new FileReader();
		reader.onload = async () => {
			setNote(null);
			setBusy(true);
			try {
				const parsed = JSON.parse(String(reader.result));
				const messages = Array.isArray(parsed) ? parsed : parsed.messages;
				const res = await sessionApi.importConversation(messages, parsed.title);
				if (res.thread_id) {
					qc.invalidateQueries({ queryKey: ["sessions"] });
					selectThread(res.thread_id);
					setNote(t("conversation.imported", { count: res.count ?? 0 }));
				} else {
					setNote(res.error || t("conversation.importFailed"));
				}
			} catch {
				setNote(t("conversation.readError"));
			} finally {
				setBusy(false);
			}
		};
		reader.readAsText(file);
	};

	const onClear = () => {
		remove.mutate(threadId);
		newChat();
		setNote(t("conversation.cleared"));
	};

	return (
		<div className="mx-auto max-w-2xl space-y-3">
			<div className="flex flex-wrap gap-2">
				<Button variant="outline" onClick={onTranscript} disabled={busy}>
					{t("conversation.transcript")}
				</Button>
				<Button variant="outline" onClick={onJson} disabled={busy}>
					{t("conversation.json")}
				</Button>
				<Button
					variant="outline"
					onClick={() => fileRef.current?.click()}
					disabled={busy}
				>
					{t("conversation.import")}
				</Button>
				<Button variant="outline" onClick={onClear}>
					{t("conversation.clear")}
				</Button>
				<input
					ref={fileRef}
					type="file"
					accept=".json,application/json"
					className="hidden"
					onChange={onImportFile}
				/>
			</div>
			<p className="text-[11px] text-muted-foreground">
				{t("conversation.desc")}
			</p>
			{note && <p className="text-xs text-foreground">{note}</p>}
		</div>
	);
}
