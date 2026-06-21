import { useEffect, useState } from "react";
import { useMemory, useWriteMemory } from "@/api/queries";
import type { MemorySection } from "@/api/types";
import { PanelLayout } from "@/components/layout/PanelLayout";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

const SECTIONS: { key: MemorySection; label: string; hint: string }[] = [
	{ key: "memory", label: "Notes", hint: "Long-term notes the agent keeps." },
	{ key: "user", label: "About you", hint: "Profile facts about the user." },
	{ key: "soul", label: "Persona", hint: "The agent's character / soul." },
];

export function MemoryPanel() {
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
		<PanelLayout
			title="Memory"
			description="Per-user memory injected into the agent's system prompt."
		>
			<Tabs defaultValue="memory">
				<TabsList>
					{SECTIONS.map((s) => (
						<TabsTrigger key={s.key} value={s.key}>
							{s.label}
						</TabsTrigger>
					))}
				</TabsList>
				{SECTIONS.map((s) => (
					<TabsContent key={s.key} value={s.key} className="space-y-2">
						<p className="text-xs text-muted-foreground">{s.hint}</p>
						<Textarea
							value={draft[s.key]}
							onChange={(e) =>
								setDraft((d) => ({ ...d, [s.key]: e.target.value }))
							}
							className="min-h-[300px] font-mono text-xs"
							placeholder="(empty)"
						/>
						<Button
							size="sm"
							disabled={write.isPending}
							onClick={() =>
								write.mutate({ section: s.key, content: draft[s.key] })
							}
						>
							{write.isPending ? "Saving…" : "Save"}
						</Button>
					</TabsContent>
				))}
			</Tabs>
		</PanelLayout>
	);
}
