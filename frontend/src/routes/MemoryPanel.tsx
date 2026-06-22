import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMemory, useWriteMemory } from "@/api/queries";
import { PanelLayout } from "@/components/layout/PanelLayout";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

// Single per-user long-term memory doc (deepagents AGENTS.md convention). The
// agent reads it via MemoryMiddleware and updates it with edit_file; this panel
// edits the same content.
export function MemoryPanel() {
	const { t } = useTranslation();
	const { data } = useMemory();
	const write = useWriteMemory();
	const [draft, setDraft] = useState("");

	// Seed the editable draft once the saved memory loads.
	useEffect(() => {
		if (data) setDraft(data.agents_md ?? "");
	}, [data]);

	return (
		<PanelLayout title={t("memory.title")} description={t("memory.subtitle")}>
			<div className="space-y-2">
				<p className="text-xs text-muted-foreground">{t("memory.notesHint")}</p>
				<Textarea
					value={draft}
					onChange={(e) => setDraft(e.target.value)}
					className="min-h-[420px] font-mono text-xs"
					placeholder={t("memory.emptyPlaceholder")}
				/>
				<Button
					size="sm"
					disabled={write.isPending}
					onClick={() => write.mutate(draft)}
				>
					{write.isPending ? t("common.saving") : t("common.save")}
				</Button>
			</div>
		</PanelLayout>
	);
}
