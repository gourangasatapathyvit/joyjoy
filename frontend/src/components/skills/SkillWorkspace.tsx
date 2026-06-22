import { FilePlus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useSkillContent, useSkillMutations } from "@/api/queries";
import type { Skill } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { buildTree, FileTreeNodes } from "./fileTree";
import { ImportZipButton } from "./ImportZipButton";

// View/edit a skill as a file tree: SKILL.md + helper files. User skills are fully
// editable (edit content, add/delete files, re-import a zip); global skills are
// read-only (browse + view).
export function SkillWorkspace({
	skill,
	onDeleted,
}: {
	skill: Skill;
	onDeleted: () => void;
}) {
	const { t } = useTranslation();
	const { remove, saveFile, deleteFile } = useSkillMutations();
	const editable = skill.editable;
	const { data: meta } = useSkillContent(skill.name); // SKILL.md + linked_files
	const [sel, setSel] = useState("SKILL.md");
	const isMd = sel === "SKILL.md";
	const { data: fileData, isLoading } = useSkillContent(
		skill.name,
		isMd ? null : sel,
	);
	const current = isMd ? meta : fileData;

	const [draft, setDraft] = useState("");
	const [dirty, setDirty] = useState(false);
	const [err, setErr] = useState<string | null>(null);
	const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());
	const toggleDir = (path: string) =>
		setCollapsed((prev) => {
			const next = new Set(prev);
			next.has(path) ? next.delete(path) : next.add(path);
			return next;
		});

	useEffect(() => {
		setDraft(current?.content ?? "");
		setDirty(false);
		setErr(null);
	}, [current?.content]);

	const files = ["SKILL.md", ...Object.keys(meta?.linked_files ?? {}).sort()];
	const tree = buildTree(files);

	const onSaveFile = () => {
		setErr(null);
		saveFile.mutate(
			{ skill: skill.name, path: sel, content: draft },
			{
				onSuccess: (r) =>
					r?.ok === false
						? setErr(r.error ?? t("skills.saveFailed"))
						: setDirty(false),
				onError: () => setErr(t("skills.saveFailed")),
			},
		);
	};

	const onAddFile = () => {
		const p = window
			.prompt(t("skills.addFilePrompt", "New file path (e.g. scripts/run.py):"))
			?.trim();
		if (!p) return;
		saveFile.mutate(
			{ skill: skill.name, path: p, content: "" },
			{
				onSuccess: (r) =>
					r?.ok === false
						? window.alert(r.error)
						: setSel(p.replace(/^\/+/, "")),
			},
		);
	};

	const onDeleteFile = (p: string) => {
		if (p === "SKILL.md") return;
		if (
			!window.confirm(
				t("skills.deleteFileConfirm", { defaultValue: "Delete this file?" }),
			)
		)
			return;
		deleteFile.mutate(
			{ skill: skill.name, path: p },
			{ onSuccess: () => sel === p && setSel("SKILL.md") },
		);
	};

	const isMarkdown = sel.toLowerCase().endsWith(".md");

	return (
		<div className="flex min-h-0 flex-1 flex-col">
			<div className="flex items-center justify-between gap-3 border-b border-border px-6 py-3">
				<div className="flex min-w-0 items-center gap-2">
					<h1 className="truncate font-heading text-lg font-semibold text-foreground">
						{skill.name}
					</h1>
					<Badge variant="outline" className="shrink-0 text-[10px]">
						{skill.scope}
					</Badge>
					{!editable && (
						<Badge variant="secondary" className="shrink-0 text-[10px]">
							{t("common.readOnly")}
						</Badge>
					)}
				</div>
				{editable && (
					<div className="flex shrink-0 items-center gap-2">
						<ImportZipButton
							defaultName={skill.name}
							label={t("skills.reimport", "Re-import .zip")}
							onImported={() => setSel("SKILL.md")}
						/>
						<Button
							size="sm"
							variant="ghost"
							onClick={() =>
								remove.mutate(skill.name, { onSuccess: onDeleted })
							}
						>
							<Trash2 className="size-3.5" />{" "}
							{t("skills.deleteSkill", "Delete skill")}
						</Button>
					</div>
				)}
			</div>

			<div className="flex min-h-0 flex-1">
				{/* file tree */}
				<div className="flex w-56 shrink-0 flex-col border-r border-border bg-sidebar/50">
					<div className="flex items-center justify-between px-3 py-2">
						<span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
							{t("skills.files", "Files")}
						</span>
						{editable && (
							<button
								type="button"
								onClick={onAddFile}
								title={t("skills.addFile", "Add file")}
								className="inline-flex size-6 items-center justify-center rounded-md text-muted-foreground hover:bg-primary/10 hover:text-primary"
							>
								<FilePlus className="size-4" />
							</button>
						)}
					</div>
					<div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-2">
						<FileTreeNodes
							nodes={tree}
							depth={0}
							sel={sel}
							editable={editable}
							collapsed={collapsed}
							onToggle={toggleDir}
							onSelect={setSel}
							onDelete={onDeleteFile}
						/>
					</div>
				</div>

				{/* file content: edit (user) or view (global) */}
				<div className="flex min-h-0 flex-1 flex-col px-6 py-4">
					{isLoading ? (
						<p className="text-sm text-muted-foreground">
							{t("common.loading")}
						</p>
					) : editable ? (
						<div className="flex min-h-0 flex-1 flex-col gap-2">
							<div className="flex items-center justify-between">
								<span className="font-mono text-xs text-muted-foreground">
									{sel}
								</span>
								<Button
									size="sm"
									onClick={onSaveFile}
									disabled={!dirty || saveFile.isPending}
								>
									{saveFile.isPending ? t("common.saving") : t("common.save")}
								</Button>
							</div>
							<Textarea
								key={`${skill.name}:${sel}`}
								value={draft}
								onChange={(e) => {
									setDraft(e.target.value);
									setDirty(true);
								}}
								className="min-h-0 flex-1 resize-none font-mono text-xs"
								placeholder={isMd ? "---\nname: …\ndescription: …\n---\n" : ""}
							/>
							{err && <p className="text-xs text-destructive">{err}</p>}
						</div>
					) : isMarkdown ? (
						<div className="min-h-0 flex-1 overflow-y-auto">
							<div className="markdown-body mx-auto max-w-3xl">
								<ReactMarkdown remarkPlugins={[remarkGfm]}>
									{draft || `_${t("skills.noContent")}_`}
								</ReactMarkdown>
							</div>
						</div>
					) : (
						<pre className="min-h-0 flex-1 overflow-auto rounded-md bg-muted/40 p-3 font-mono text-xs text-foreground">
							{draft}
						</pre>
					)}
				</div>
			</div>
		</div>
	);
}
