import { Lock, Pencil, Plus, Search, Sparkles, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
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

type Mode = "view" | "edit" | "create";

// Split a SKILL.md into its YAML frontmatter + the markdown body.
function splitFrontmatter(content: string): {
	frontmatter: string | null;
	body: string;
} {
	const m = content.match(/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/);
	return m
		? { frontmatter: m[1], body: m[2] }
		: { frontmatter: null, body: content };
}

// View mode: the selected skill's content (frontmatter + rendered markdown).
function SkillDetail({
	skill,
	onEdit,
	onDelete,
}: {
	skill: Skill;
	onEdit: () => void;
	onDelete: () => void;
}) {
	const { data, isLoading } = useSkillContent(skill.name);
	const { frontmatter, body } = splitFrontmatter(data?.content ?? "");

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
					{skill.builtin && (
						<Badge variant="secondary" className="shrink-0 text-[10px]">
							built-in
						</Badge>
					)}
				</div>
				{skill.editable ? (
					<div className="flex shrink-0 items-center gap-1">
						<Button size="sm" variant="ghost" onClick={onEdit}>
							<Pencil className="size-3.5" /> Edit
						</Button>
						<Button size="sm" variant="ghost" onClick={onDelete}>
							<Trash2 className="size-3.5" /> Delete
						</Button>
					</div>
				) : (
					<Badge variant="secondary" className="shrink-0 text-[10px]">
						read-only
					</Badge>
				)}
			</div>
			<div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
				<div className="mx-auto max-w-3xl">
					{isLoading ? (
						<p className="text-sm text-muted-foreground">Loading…</p>
					) : (
						<>
							{skill.description && (
								<p className="mb-4 text-sm text-muted-foreground">
									{skill.description}
								</p>
							)}
							{frontmatter && (
								<details className="mb-4 rounded-md border border-border bg-muted/40">
									<summary className="cursor-pointer px-3 py-2 text-xs font-medium text-muted-foreground">
										Metadata
									</summary>
									<pre className="overflow-x-auto px-3 pb-3 text-xs text-muted-foreground">
										{frontmatter}
									</pre>
								</details>
							)}
							<div className="markdown-body">
								<ReactMarkdown remarkPlugins={[remarkGfm]}>
									{body || "_(no content)_"}
								</ReactMarkdown>
							</div>
						</>
					)}
				</div>
			</div>
		</div>
	);
}

// Create / edit mode: inline editor in the right pane (no popup). On edit the
// content is fetched and the name is locked (saving under a new name = a new
// skill). Save/Cancel live in the pane header, like the webui.
function SkillEditor({
	name,
	onSaved,
	onCancel,
}: {
	name: string | null;
	onSaved: (name: string) => void;
	onCancel: () => void;
}) {
	const editing = name !== null;
	const { data, isLoading } = useSkillContent(name);
	const { save } = useSkillMutations();
	const [draftName, setDraftName] = useState(name ?? "");
	const [content, setContent] = useState("");
	const [err, setErr] = useState<string | null>(null);

	useEffect(() => {
		if (editing && data?.content != null) setContent(data.content);
	}, [editing, data?.content]);

	const onSave = () => {
		const n = draftName.trim();
		if (!n) return;
		setErr(null);
		save.mutate(
			{ name: n, content },
			{
				onSuccess: (res) => {
					if (res?.ok === false) setErr(res.error ?? "Save failed");
					else onSaved(n);
				},
				onError: () => setErr("Save failed"),
			},
		);
	};

	return (
		<div className="flex min-h-0 flex-1 flex-col">
			<div className="flex items-center justify-between gap-3 border-b border-border px-6 py-3">
				<h1 className="truncate font-heading text-lg font-semibold text-foreground">
					{editing ? `Edit ${name}` : "New skill"}
				</h1>
				<div className="flex shrink-0 items-center gap-2">
					<Button size="sm" variant="ghost" onClick={onCancel}>
						Cancel
					</Button>
					<Button
						size="sm"
						onClick={onSave}
						disabled={!draftName.trim() || save.isPending}
					>
						{save.isPending ? "Saving…" : "Save"}
					</Button>
				</div>
			</div>
			<div className="min-h-0 flex-1 px-6 py-5">
				<div className="mx-auto flex h-full min-h-0 w-full max-w-3xl flex-col gap-3">
					{!editing && (
						<div className="space-y-1.5">
							<Label htmlFor="skill-name">Name</Label>
							<Input
								id="skill-name"
								value={draftName}
								onChange={(e) => setDraftName(e.target.value)}
								placeholder="my-skill"
							/>
						</div>
					)}
					<div className="flex min-h-0 flex-1 flex-col gap-1.5">
						<Label htmlFor="skill-content">SKILL.md content</Label>
						{editing && isLoading ? (
							<p className="text-sm text-muted-foreground">Loading…</p>
						) : (
							<Textarea
								id="skill-content"
								value={content}
								onChange={(e) => setContent(e.target.value)}
								className="min-h-0 flex-1 resize-none font-mono text-xs"
								placeholder={
									"---\nname: my-skill\ndescription: what it does\n---\n\nInstructions…"
								}
							/>
						)}
					</div>
					{err && <p className="text-xs text-destructive">{err}</p>}
				</div>
			</div>
		</div>
	);
}

// Skills = webui-style master/detail: searchable list on the left; the right
// pane views the selected skill OR hosts the inline create/edit editor.
export function SkillsPanel() {
	const { data, isLoading } = useSkills();
	const { remove, toggle } = useSkillMutations();
	const skills = data?.skills ?? [];

	const [query, setQuery] = useState("");
	const [selected, setSelected] = useState<string | null>(null);
	const [mode, setMode] = useState<Mode>("view");

	const q = query.trim().toLowerCase();
	const filtered = q
		? skills.filter((s) =>
				`${s.name} ${s.description ?? ""}`.toLowerCase().includes(q),
			)
		: skills;
	const selectedSkill = skills.find((s) => s.name === selected) ?? null;

	const selectSkill = (n: string) => {
		setSelected(n);
		setMode("view");
	};
	const startCreate = () => setMode("create");
	const startEdit = () => setMode("edit");
	const cancelEditor = () => setMode("view");
	const afterSave = (n: string) => {
		setSelected(n);
		setMode("view");
	};
	const onDelete = (n: string) => {
		remove.mutate(n);
		if (selected === n) {
			setSelected(null);
			setMode("view");
		}
	};

	return (
		<div className="flex min-h-0 flex-1">
			<aside className="flex w-[300px] shrink-0 flex-col border-r border-border bg-sidebar">
				<div className="flex items-center justify-between px-4 py-3">
					<span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
						Skills
					</span>
					<button
						type="button"
						onClick={startCreate}
						title="New skill"
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
						placeholder="Search skills..."
						className="w-full rounded-lg border border-border bg-background py-[7px] pr-8 pl-8 text-[13px] outline-none transition-[box-shadow,border-color] placeholder:text-muted-foreground focus:border-primary focus:ring-[3px] focus:ring-primary/15"
					/>
					{query && (
						<button
							type="button"
							onClick={() => setQuery("")}
							title="Clear"
							className="-translate-y-1/2 absolute top-1/2 right-[18px] inline-flex size-6 items-center justify-center rounded-md text-muted-foreground hover:text-foreground"
						>
							<X className="size-3.5" />
						</button>
					)}
				</div>

				<div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
					{isLoading ? (
						<p className="px-2 py-4 text-xs text-muted-foreground">Loading…</p>
					) : filtered.length === 0 ? (
						<p className="px-2 py-4 text-xs text-muted-foreground">
							{q ? "No matches." : "No skills found."}
						</p>
					) : (
						<ul className="flex flex-col gap-0.5">
							{filtered.map((s) => {
								const active = s.name === selected && mode !== "create";
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
												onClick={() => selectSkill(s.name)}
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
													onCheckedChange={(v) =>
														toggle.mutate({ name: s.name, enabled: v })
													}
													aria-label={
														s.enabled ? "Disable skill" : "Enable skill"
													}
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
				{mode === "create" ? (
					<SkillEditor
						key="__new__"
						name={null}
						onSaved={afterSave}
						onCancel={cancelEditor}
					/>
				) : mode === "edit" && selectedSkill ? (
					<SkillEditor
						key={selectedSkill.name}
						name={selectedSkill.name}
						onSaved={afterSave}
						onCancel={cancelEditor}
					/>
				) : selectedSkill ? (
					<SkillDetail
						key={selectedSkill.name}
						skill={selectedSkill}
						onEdit={startEdit}
						onDelete={() => onDelete(selectedSkill.name)}
					/>
				) : (
					<div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
						<Sparkles className="size-8 text-muted-foreground opacity-40" />
						<div className="space-y-1">
							<p className="text-sm font-medium text-foreground">
								Select a skill
							</p>
							<p className="mx-auto max-w-xs text-xs text-muted-foreground">
								Pick a skill from the list to view its contents, or create a new
								one.
							</p>
						</div>
						<Button size="sm" variant="outline" onClick={startCreate}>
							<Plus className="size-3.5" /> New skill
						</Button>
					</div>
				)}
			</main>
		</div>
	);
}
