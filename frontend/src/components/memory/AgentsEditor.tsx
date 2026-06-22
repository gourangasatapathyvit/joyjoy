import { Pencil } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMemory, useWriteMemory } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DocBody } from "./DocBody";

// AGENTS.md — always-loaded core memory. View (markdown) / Edit (textarea).
export function AgentsEditor() {
	const { t } = useTranslation();
	const { data } = useMemory();
	const write = useWriteMemory();
	const [editing, setEditing] = useState(false);
	const [draft, setDraft] = useState("");
	const [dirty, setDirty] = useState(false);
	useEffect(() => {
		setDraft(data?.agents_md ?? "");
		setDirty(false);
		setEditing(false);
	}, [data?.agents_md]);

	return (
		<div className="flex min-h-0 flex-1 flex-col">
			<div className="flex items-center justify-between gap-3 border-b border-border px-6 py-3">
				<div className="flex min-w-0 items-center gap-2">
					<h1 className="font-heading text-lg font-semibold text-foreground">
						AGENTS.md
					</h1>
					<Badge variant="secondary" className="shrink-0 text-[10px]">
						{t("memory.alwaysLoaded")}
					</Badge>
				</div>
				<div className="flex shrink-0 items-center gap-2">
					{editing ? (
						<>
							<Button
								size="sm"
								variant="ghost"
								onClick={() => {
									setDraft(data?.agents_md ?? "");
									setDirty(false);
									setEditing(false);
								}}
							>
								{t("common.cancel")}
							</Button>
							<Button
								size="sm"
								disabled={!dirty || write.isPending}
								onClick={() =>
									write.mutate(draft, { onSuccess: () => setEditing(false) })
								}
							>
								{write.isPending ? t("common.saving") : t("common.save")}
							</Button>
						</>
					) : (
						<Button
							size="sm"
							variant="outline"
							onClick={() => setEditing(true)}
						>
							<Pencil className="size-3.5" /> {t("common.edit")}
						</Button>
					)}
				</div>
			</div>
			<div className="flex min-h-0 flex-1 flex-col gap-2 px-6 py-4">
				<p className="text-xs text-muted-foreground">{t("memory.notesHint")}</p>
				<DocBody
					editing={editing}
					name="AGENTS.md"
					draft={draft}
					onChange={(v) => {
						setDraft(v);
						setDirty(true);
					}}
				/>
			</div>
		</div>
	);
}
