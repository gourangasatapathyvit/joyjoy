import {
	ChevronDown,
	ChevronRight,
	FilePlus,
	FileText,
	Folder,
	Lock,
	Plus,
	Search,
	Sparkles,
	Trash2,
	Upload,
	X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useSkillContent, useSkillMutations, useSkills } from "@/api/queries";
import type { Skill } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

// Read a File into a base64 string (for the zip-import endpoint).
async function fileToBase64(file: File): Promise<string> {
	const bytes = new Uint8Array(await file.arrayBuffer());
	let bin = "";
	for (let i = 0; i < bytes.length; i += 0x8000) {
		bin += String.fromCharCode(...Array.from(bytes.subarray(i, i + 0x8000)));
	}
	return btoa(bin);
}

// Import a skill folder from a .zip (SKILL.md + helper tree). Used both to create
// a new skill and to re-import/replace an existing one.
function ImportZipButton({
	defaultName,
	onImported,
	label,
}: {
	defaultName?: string;
	onImported: (name: string) => void;
	label: string;
}) {
	const { t } = useTranslation();
	const { importZip } = useSkillMutations();
	const inputRef = useRef<HTMLInputElement>(null);

	const onPick = async (file: File) => {
		const base = file.name.replace(/\.zip$/i, "");
		const name = (
			defaultName ??
			window.prompt(t("skills.importNamePrompt", "Name for the imported skill:"), base) ??
			""
		).trim();
		if (!name) return;
		const zip_b64 = await fileToBase64(file);
		importZip.mutate(
			{ name, zip_b64 },
			{
				onSuccess: (r) => {
					if (r?.ok === false) window.alert(r.error ?? "import failed");
					else onImported(name);
				},
			},
		);
	};

	return (
		<>
			<input
				ref={inputRef}
				type="file"
				accept=".zip,application/zip"
				className="hidden"
				onChange={(e) => {
					const f = e.target.files?.[0];
					if (f) onPick(f);
					e.target.value = "";
				}}
			/>
			<Button
				size="sm"
				variant="outline"
				onClick={() => inputRef.current?.click()}
				disabled={importZip.isPending}
			>
				<Upload className="size-3.5" />{" "}
				{importZip.isPending ? t("common.saving") : label}
			</Button>
		</>
	);
}

// Create a brand-new skill (name + initial SKILL.md). Adding helper files happens
// afterward in the workspace.
function CreateSkillForm({
	onSaved,
	onCancel,
}: {
	onSaved: (name: string) => void;
	onCancel: () => void;
}) {
	const { t } = useTranslation();
	const { save } = useSkillMutations();
	const [name, setName] = useState("");
	const [content, setContent] = useState("");
	const [err, setErr] = useState<string | null>(null);

	const onSave = () => {
		const n = name.trim();
		if (!n) return;
		setErr(null);
		save.mutate(
			{ name: n, content },
			{
				onSuccess: (r) =>
					r?.ok === false
						? setErr(r.error ?? t("skills.saveFailed"))
						: onSaved(n),
				onError: () => setErr(t("skills.saveFailed")),
			},
		);
	};

	return (
		<div className="flex min-h-0 flex-1 flex-col">
			<div className="flex items-center justify-between gap-3 border-b border-border px-6 py-3">
				<h1 className="font-heading text-lg font-semibold text-foreground">
					{t("skills.newTitle")}
				</h1>
				<div className="flex shrink-0 items-center gap-2">
					<Button size="sm" variant="ghost" onClick={onCancel}>
						{t("common.cancel")}
					</Button>
					<Button size="sm" onClick={onSave} disabled={!name.trim() || save.isPending}>
						{save.isPending ? t("common.saving") : t("common.save")}
					</Button>
				</div>
			</div>
			<div className="min-h-0 flex-1 px-6 py-5">
				<div className="mx-auto flex h-full min-h-0 w-full max-w-3xl flex-col gap-3">
					<div className="space-y-1.5">
						<Label htmlFor="skill-name">{t("skills.nameLabel")}</Label>
						<Input
							id="skill-name"
							value={name}
							onChange={(e) => setName(e.target.value)}
							placeholder={t("skills.namePlaceholder")}
						/>
					</div>
					<div className="flex min-h-0 flex-1 flex-col gap-1.5">
						<Label htmlFor="skill-content">SKILL.md</Label>
						<Textarea
							id="skill-content"
							value={content}
							onChange={(e) => setContent(e.target.value)}
							className="min-h-0 flex-1 resize-none font-mono text-xs"
							placeholder={"---\nname: my-skill\ndescription: what it does\n---\n\nInstructions…"}
						/>
					</div>
					<p className="text-xs text-muted-foreground">
						{t("skills.createHint", "Add helper files (scripts/, references/, …) after saving — or import a .zip.")}
					</p>
					{err && <p className="text-xs text-destructive">{err}</p>}
				</div>
			</div>
		</div>
	);
}

// Build a nested folder tree from flat relative paths (e.g. "scripts/run.py").
type TreeNode = { name: string; path: string; dir: boolean; children: TreeNode[] };

function buildTree(paths: string[]): TreeNode[] {
	const roots: TreeNode[] = [];
	for (const p of paths) {
		const segs = p.split("/").filter(Boolean);
		let level = roots;
		let acc = "";
		segs.forEach((seg, i) => {
			acc = acc ? `${acc}/${seg}` : seg;
			const isFile = i === segs.length - 1;
			let node = level.find((n) => n.name === seg && n.dir === !isFile);
			if (!node) {
				node = { name: seg, path: isFile ? p : acc, dir: !isFile, children: [] };
				level.push(node);
			}
			level = node.children;
		});
	}
	const sort = (ns: TreeNode[]) => {
		ns.sort((a, b) => (a.dir !== b.dir ? (a.dir ? -1 : 1) : a.name.localeCompare(b.name)));
		for (const n of ns) sort(n.children);
	};
	sort(roots);
	roots.sort((a, b) => (a.name === "SKILL.md" ? -1 : b.name === "SKILL.md" ? 1 : 0)); // SKILL.md first
	return roots;
}

// Recursive tree rows: folders collapse/expand; files select; editable files get a delete.
function FileTreeNodes({
	nodes,
	depth,
	sel,
	editable,
	collapsed,
	onToggle,
	onSelect,
	onDelete,
}: {
	nodes: TreeNode[];
	depth: number;
	sel: string;
	editable: boolean;
	collapsed: Set<string>;
	onToggle: (path: string) => void;
	onSelect: (path: string) => void;
	onDelete: (path: string) => void;
}) {
	return (
		<>
			{nodes.map((n) => {
				const pad = { paddingLeft: `${depth * 12 + 8}px` };
				if (n.dir) {
					const open = !collapsed.has(n.path);
					return (
						<div key={`d:${n.path}`}>
							<button
								type="button"
								onClick={() => onToggle(n.path)}
								style={pad}
								className="flex w-full items-center gap-1 rounded-md py-1 pr-2 text-left hover:bg-foreground/5"
							>
								{open ? (
									<ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
								) : (
									<ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
								)}
								<Folder className="size-3.5 shrink-0 text-muted-foreground" />
								<span className="truncate font-mono text-[12px] text-foreground">{n.name}</span>
							</button>
							{open && (
								<FileTreeNodes
									nodes={n.children}
									depth={depth + 1}
									sel={sel}
									editable={editable}
									collapsed={collapsed}
									onToggle={onToggle}
									onSelect={onSelect}
									onDelete={onDelete}
								/>
							)}
						</div>
					);
				}
				const active = n.path === sel;
				return (
					<div
						key={`f:${n.path}`}
						style={pad}
						className={cn(
							"group flex items-center gap-1.5 rounded-md py-1 pr-2",
							active ? "bg-primary/10" : "hover:bg-foreground/5",
						)}
					>
						<button
							type="button"
							onClick={() => onSelect(n.path)}
							className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
						>
							<FileText className="size-3.5 shrink-0 text-muted-foreground" />
							<span
								className={cn(
									"truncate font-mono text-[12px]",
									active ? "text-primary" : "text-foreground",
									n.path === "SKILL.md" && "font-semibold",
								)}
							>
								{n.name}
							</span>
						</button>
						{editable && n.path !== "SKILL.md" && (
							<button
								type="button"
								onClick={() => onDelete(n.path)}
								title="Delete"
								className="shrink-0 text-muted-foreground opacity-0 hover:text-destructive group-hover:opacity-100"
							>
								<X className="size-3.5" />
							</button>
						)}
					</div>
				);
			})}
		</>
	);
}

// View/edit a skill as a file tree: SKILL.md + helper files. User skills are fully
// editable (edit content, add/delete files, re-import a zip); global skills are
// read-only (browse + view).
function SkillWorkspace({
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
	const { data: fileData, isLoading } = useSkillContent(skill.name, isMd ? null : sel);
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
					r?.ok === false ? setErr(r.error ?? t("skills.saveFailed")) : setDirty(false),
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
			{ onSuccess: (r) => (r?.ok === false ? window.alert(r.error) : setSel(p.replace(/^\/+/, ""))) },
		);
	};

	const onDeleteFile = (p: string) => {
		if (p === "SKILL.md") return;
		if (!window.confirm(t("skills.deleteFileConfirm", { defaultValue: "Delete this file?" }))) return;
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
						<Button size="sm" variant="ghost" onClick={() => remove.mutate(skill.name, { onSuccess: onDeleted })}>
							<Trash2 className="size-3.5" /> {t("skills.deleteSkill", "Delete skill")}
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
						<p className="text-sm text-muted-foreground">{t("common.loading")}</p>
					) : editable ? (
						<div className="flex min-h-0 flex-1 flex-col gap-2">
							<div className="flex items-center justify-between">
								<span className="font-mono text-xs text-muted-foreground">{sel}</span>
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

// Skills = master/detail: searchable list on the left; the right pane is a
// per-skill file workspace (SKILL.md + helper tree) or the create form.
export function SkillsPanel() {
	const { t } = useTranslation();
	const { data, isLoading } = useSkills();
	const { toggle } = useSkillMutations();
	const skills = data?.skills ?? [];

	const [query, setQuery] = useState("");
	const [selected, setSelected] = useState<string | null>(null);
	const [creating, setCreating] = useState(false);

	const q = query.trim().toLowerCase();
	const filtered = q
		? skills.filter((s) => `${s.name} ${s.description ?? ""}`.toLowerCase().includes(q))
		: skills;
	const selectedSkill = skills.find((s) => s.name === selected) ?? null;

	const pick = (n: string) => {
		setSelected(n);
		setCreating(false);
	};

	return (
		<div className="flex min-h-0 flex-1">
			<aside className="flex w-[300px] shrink-0 flex-col border-r border-border bg-sidebar">
				<div className="flex items-center justify-between gap-1 px-4 py-3">
					<span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
						{t("skills.title")}
					</span>
					<div className="flex items-center gap-1">
						<ImportZipButton
							label={t("skills.import", "Import .zip")}
							onImported={pick}
						/>
						<button
							type="button"
							onClick={() => {
								setCreating(true);
								setSelected(null);
							}}
							title={t("skills.newSkill")}
							className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary"
						>
							<Plus className="size-4" />
						</button>
					</div>
				</div>

				<div className="relative px-3 pb-2">
					<Search className="-translate-y-1/2 pointer-events-none absolute top-1/2 left-[22px] size-3.5 text-muted-foreground opacity-70" />
					<input
						value={query}
						onChange={(e) => setQuery(e.target.value)}
						placeholder={t("skills.searchPlaceholder")}
						className="w-full rounded-lg border border-border bg-background py-[7px] pr-8 pl-8 text-[13px] outline-none transition-[box-shadow,border-color] placeholder:text-muted-foreground focus:border-primary focus:ring-[3px] focus:ring-primary/15"
					/>
					{query && (
						<button
							type="button"
							onClick={() => setQuery("")}
							className="-translate-y-1/2 absolute top-1/2 right-[18px] inline-flex size-6 items-center justify-center rounded-md text-muted-foreground hover:text-foreground"
						>
							<X className="size-3.5" />
						</button>
					)}
				</div>

				<div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
					{isLoading ? (
						<p className="px-2 py-4 text-xs text-muted-foreground">{t("common.loading")}</p>
					) : filtered.length === 0 ? (
						<p className="px-2 py-4 text-xs text-muted-foreground">
							{q ? t("common.noMatches") : t("skills.none")}
						</p>
					) : (
						<ul className="flex flex-col gap-0.5">
							{filtered.map((s) => {
								const active = s.name === selected && !creating;
								return (
									<li key={`${s.scope}-${s.name}`}>
										<div
											className={cn(
												"group flex items-center gap-2 rounded-lg px-2 py-2 transition-colors",
												active ? "bg-primary/10" : "hover:bg-foreground/5",
											)}
										>
											<button
												type="button"
												onClick={() => pick(s.name)}
												className={cn(
													"flex min-w-0 flex-1 flex-col gap-0.5 text-left",
													s.editable && !s.enabled && "opacity-55",
												)}
											>
												<span
													className={cn(
														"truncate text-[13px] font-medium",
														active ? "text-primary" : "text-foreground",
													)}
												>
													{s.name}
												</span>
												{s.description && (
													<span className="truncate text-[11px] text-muted-foreground">
														{s.description}
													</span>
												)}
											</button>
											{s.editable ? (
												<Switch
													checked={s.enabled}
													onCheckedChange={(v) => toggle.mutate({ name: s.name, enabled: v })}
													aria-label={s.enabled ? t("skills.disable") : t("skills.enable")}
													className="shrink-0"
												/>
											) : (
												<Lock className="size-3.5 shrink-0 text-muted-foreground opacity-60" />
											)}
										</div>
									</li>
								);
							})}
						</ul>
					)}
				</div>
			</aside>

			<main className="flex min-h-0 flex-1 flex-col">
				{creating ? (
					<CreateSkillForm onSaved={pick} onCancel={() => setCreating(false)} />
				) : selectedSkill ? (
					<SkillWorkspace
						key={selectedSkill.name}
						skill={selectedSkill}
						onDeleted={() => setSelected(null)}
					/>
				) : (
					<div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
						<Sparkles className="size-8 text-muted-foreground opacity-40" />
						<div className="space-y-1">
							<p className="text-sm font-medium text-foreground">{t("skills.selectTitle")}</p>
							<p className="mx-auto max-w-xs text-xs text-muted-foreground">
								{t("skills.selectHint")}
							</p>
						</div>
						<Button size="sm" variant="outline" onClick={() => setCreating(true)}>
							<Plus className="size-3.5" /> {t("skills.newSkill")}
						</Button>
					</div>
				)}
			</main>
		</div>
	);
}
