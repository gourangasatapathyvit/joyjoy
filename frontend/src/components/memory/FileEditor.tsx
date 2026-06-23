import { Pencil, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMemoryFile, useMemoryFileMutations } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { stripLeadingSlash } from "@/lib/text";
import { DocBody } from "./DocBody";

// A dynamic /memories/ file. View (markdown/text) / Edit (textarea) + Delete.
export function FileEditor({
	path,
	onDeleted,
}: {
	path: string;
	onDeleted: () => void;
}) {
	const { t } = useTranslation();
	const { data, isLoading } = useMemoryFile(path);
	const { save, remove } = useMemoryFileMutations();
	const [editing, setEditing] = useState(false);
	const [draft, setDraft] = useState("");
	const [dirty, setDirty] = useState(false);
	useEffect(() => {
		setDraft(data?.content ?? "");
		setDirty(false);
		setEditing(false);
	}, [data?.content]);

	return (
		<div className="flex min-h-0 flex-1 flex-col">
			<div className="flex items-center justify-between gap-3 border-b border-border px-6 py-3">
				<div className="flex min-w-0 items-center gap-2">
					<h1 className="truncate font-heading text-lg font-semibold text-foreground">
						{stripLeadingSlash(path)}
					</h1>
					{data && data.enabled === false && (
						<Badge variant="outline" className="shrink-0 text-[10px]">
							{t("memory.disabledBadge")}
						</Badge>
					)}
				</div>
				<div className="flex shrink-0 items-center gap-2">
					<Button
						size="sm"
						variant="ghost"
						className="text-destructive"
						onClick={() => remove.mutate(path, { onSuccess: onDeleted })}
					>
						<Trash2 className="size-3.5" /> {t("common.delete")}
					</Button>
					{editing ? (
						<>
							<Button
								size="sm"
								variant="ghost"
								onClick={() => {
									setDraft(data?.content ?? "");
									setDirty(false);
									setEditing(false);
								}}
							>
								{t("common.cancel")}
							</Button>
							<Button
								size="sm"
								disabled={!dirty || save.isPending}
								onClick={() =>
									save.mutate(
										{ path, content: draft },
										{ onSuccess: () => setEditing(false) },
									)
								}
							>
								{save.isPending ? t("common.saving") : t("common.save")}
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
				<span className="font-mono text-xs text-muted-foreground">{path}</span>
				<DocBody
					editing={editing}
					name={path}
					draft={draft}
					loading={isLoading}
					onChange={(v) => {
						setDraft(v);
						setDirty(true);
					}}
				/>
			</div>
		</div>
	);
}
