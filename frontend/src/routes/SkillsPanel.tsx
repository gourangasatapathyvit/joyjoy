import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { useSkillContent, useSkillMutations, useSkills } from "@/api/queries";
import { PanelLayout } from "@/components/layout/PanelLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

function SkillContentDialog({
	name,
	onClose,
}: {
	name: string | null;
	onClose: () => void;
}) {
	const { data, isLoading } = useSkillContent(name);
	return (
		<Dialog open={!!name} onOpenChange={(open) => !open && onClose()}>
			<DialogContent className="max-w-2xl">
				<DialogHeader>
					<DialogTitle className="font-mono text-sm">{name}</DialogTitle>
				</DialogHeader>
				<ScrollArea className="max-h-[60vh]">
					{isLoading ? (
						<p className="text-sm text-muted-foreground">Loading…</p>
					) : (
						<pre className="whitespace-pre-wrap rounded bg-muted p-3 text-xs text-muted-foreground">
							{data?.content ?? data?.error ?? "(empty)"}
						</pre>
					)}
				</ScrollArea>
			</DialogContent>
		</Dialog>
	);
}

// Create (name === null) or edit an existing user skill. On edit, the content
// is fetched and the name is locked (saving under a new name = a new skill).
function SkillEditorDialog({
	name,
	onClose,
}: {
	name: string | null;
	onClose: () => void;
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
				onSuccess: (res) =>
					res?.ok === false ? setErr(res.error ?? "Save failed") : onClose(),
				onError: () => setErr("Save failed"),
			},
		);
	};

	return (
		<Dialog open onOpenChange={(o) => !o && onClose()}>
			<DialogContent className="max-w-2xl">
				<DialogHeader>
					<DialogTitle>{editing ? `Edit ${name}` : "New skill"}</DialogTitle>
				</DialogHeader>
				<div className="space-y-3">
					<div className="space-y-1.5">
						<Label htmlFor="skill-name">Name</Label>
						<Input
							id="skill-name"
							value={draftName}
							disabled={editing}
							onChange={(e) => setDraftName(e.target.value)}
							placeholder="my-skill"
						/>
					</div>
					<div className="space-y-1.5">
						<Label htmlFor="skill-content">SKILL.md content</Label>
						{editing && isLoading ? (
							<p className="text-sm text-muted-foreground">Loading…</p>
						) : (
							<Textarea
								id="skill-content"
								value={content}
								onChange={(e) => setContent(e.target.value)}
								rows={16}
								className="font-mono text-xs"
								placeholder={
									"---\nname: my-skill\ndescription: what it does\n---\n\nInstructions…"
								}
							/>
						)}
					</div>
					{err && <p className="text-xs text-destructive">{err}</p>}
					<div className="flex justify-end gap-2">
						<Button variant="ghost" onClick={onClose}>
							Cancel
						</Button>
						<Button
							onClick={onSave}
							disabled={!draftName.trim() || save.isPending}
						>
							{save.isPending ? "Saving…" : "Save"}
						</Button>
					</div>
				</div>
			</DialogContent>
		</Dialog>
	);
}

export function SkillsPanel() {
	const { data, isLoading } = useSkills();
	const { toggle, remove } = useSkillMutations();
	const [viewing, setViewing] = useState<string | null>(null);
	const [editorOpen, setEditorOpen] = useState(false);
	const [editName, setEditName] = useState<string | null>(null);
	const skills = data?.skills ?? [];

	const openNew = () => {
		setEditName(null);
		setEditorOpen(true);
	};
	const openEdit = (n: string) => {
		setEditName(n);
		setEditorOpen(true);
	};

	return (
		<PanelLayout
			title="Skills"
			description="Reusable agent skills (global skills are read-only)."
		>
			<div className="flex justify-end">
				<Button size="sm" variant="outline" onClick={openNew}>
					<Plus className="size-3.5" /> New skill
				</Button>
			</div>
			{isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
			{!isLoading && skills.length === 0 && (
				<p className="text-sm text-muted-foreground">No skills found.</p>
			)}
			{skills.map((sk) => (
				<Card
					key={`${sk.scope}-${sk.name}`}
					className="flex-row items-center justify-between gap-3 p-3"
				>
					<div className="min-w-0">
						<div className="flex flex-wrap items-center gap-2">
							<span className="font-medium">{sk.name}</span>
							<Badge variant="outline" className="text-[10px]">
								{sk.scope}
							</Badge>
							{sk.builtin && (
								<Badge variant="secondary" className="text-[10px]">
									built-in
								</Badge>
							)}
						</div>
						{sk.description && (
							<p className="truncate text-xs text-muted-foreground">
								{sk.description}
							</p>
						)}
					</div>
					<div className="flex shrink-0 items-center gap-2">
						<Button
							size="sm"
							variant="ghost"
							onClick={() => setViewing(sk.name)}
						>
							View
						</Button>
						{sk.editable ? (
							<>
								<Button
									size="sm"
									variant="ghost"
									onClick={() => openEdit(sk.name)}
								>
									Edit
								</Button>
								<Switch
									checked={sk.enabled}
									onCheckedChange={(enabled) =>
										toggle.mutate({ name: sk.name, enabled })
									}
								/>
								<Button
									size="sm"
									variant="ghost"
									onClick={() => remove.mutate(sk.name)}
								>
									Delete
								</Button>
							</>
						) : (
							<Badge variant="secondary" className="text-[10px]">
								read-only
							</Badge>
						)}
					</div>
				</Card>
			))}
			<SkillContentDialog name={viewing} onClose={() => setViewing(null)} />
			{editorOpen && (
				<SkillEditorDialog
					key={editName ?? "__new__"}
					name={editName}
					onClose={() => setEditorOpen(false)}
				/>
			)}
		</PanelLayout>
	);
}
