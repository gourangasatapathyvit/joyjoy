import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMemoryFileMutations } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

// Create a new /memories/ file (name + content).
export function NewFileForm({
	onSaved,
	onCancel,
}: {
	onSaved: (path: string) => void;
	onCancel: () => void;
}) {
	const { t } = useTranslation();
	const { save } = useMemoryFileMutations();
	const [name, setName] = useState("");
	const [content, setContent] = useState("");

	const onSave = () => {
		const n = name.trim();
		if (!n) return;
		save.mutate(
			{ path: n, content },
			{
				onSuccess: (r) =>
					r?.ok !== false && onSaved(n.startsWith("/") ? n : `/${n}`),
			},
		);
	};

	return (
		<div className="flex min-h-0 flex-1 flex-col">
			<div className="flex items-center justify-between gap-3 border-b border-border px-6 py-3">
				<h1 className="font-heading text-lg font-semibold text-foreground">
					{t("memory.newFile")}
				</h1>
				<div className="flex shrink-0 items-center gap-2">
					<Button size="sm" variant="ghost" onClick={onCancel}>
						{t("common.cancel")}
					</Button>
					<Button
						size="sm"
						onClick={onSave}
						disabled={!name.trim() || save.isPending}
					>
						{save.isPending ? t("common.saving") : t("common.save")}
					</Button>
				</div>
			</div>
			<div className="flex min-h-0 flex-1 flex-col gap-3 px-6 py-4">
				<Input
					value={name}
					onChange={(e) => setName(e.target.value)}
					placeholder={t("memory.filenamePlaceholder")}
					className="font-mono text-xs"
				/>
				<Textarea
					value={content}
					onChange={(e) => setContent(e.target.value)}
					className="min-h-0 flex-1 resize-none font-mono text-xs"
					placeholder={t("memory.emptyPlaceholder")}
				/>
				<p className="text-xs text-muted-foreground">
					{t("memory.newFileHint")}
				</p>
			</div>
		</div>
	);
}
