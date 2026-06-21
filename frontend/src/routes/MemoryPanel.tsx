import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMemory, useWriteMemory } from "@/api/queries";
import type { MemorySection } from "@/api/types";
import { PanelLayout } from "@/components/layout/PanelLayout";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

const SECTIONS: { key: MemorySection; labelKey: string; hintKey: string }[] = [
	{ key: "memory", labelKey: "memory.notes", hintKey: "memory.notesHint" },
	{ key: "user", labelKey: "memory.aboutYou", hintKey: "memory.aboutYouHint" },
	{ key: "soul", labelKey: "memory.persona", hintKey: "memory.personaHint" },
];

export function MemoryPanel() {
	const { t } = useTranslation();
	const { data } = useMemory();
	const write = useWriteMemory();
	const [draft, setDraft] = useState<Record<MemorySection, string>>({
		memory: "",
		user: "",
		soul: "",
	});

	// Seed the editable drafts once the saved memory loads.
	useEffect(() => {
		if (data) {
			setDraft({
				memory: data.memory ?? "",
				user: data.user ?? "",
				soul: data.soul ?? "",
			});
		}
	}, [data]);

	return (
		<PanelLayout title={t("memory.title")} description={t("memory.subtitle")}>
			<Tabs defaultValue="memory">
				<TabsList>
					{SECTIONS.map((s) => (
						<TabsTrigger key={s.key} value={s.key}>
							{t(s.labelKey)}
						</TabsTrigger>
					))}
				</TabsList>
				{SECTIONS.map((s) => (
					<TabsContent key={s.key} value={s.key} className="space-y-2">
						<p className="text-xs text-muted-foreground">{t(s.hintKey)}</p>
						<Textarea
							value={draft[s.key]}
							onChange={(e) =>
								setDraft((d) => ({ ...d, [s.key]: e.target.value }))
							}
							className="min-h-[300px] font-mono text-xs"
							placeholder={t("memory.emptyPlaceholder")}
						/>
						<Button
							size="sm"
							disabled={write.isPending}
							onClick={() =>
								write.mutate({ section: s.key, content: draft[s.key] })
							}
						>
							{write.isPending ? t("common.saving") : t("common.save")}
						</Button>
					</TabsContent>
				))}
			</Tabs>
		</PanelLayout>
	);
}
