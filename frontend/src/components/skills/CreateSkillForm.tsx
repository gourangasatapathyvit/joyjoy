import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSkillMutations } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

// Create a brand-new skill (name + initial SKILL.md). Adding helper files happens
// afterward in the workspace.
export function CreateSkillForm({
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
					<Button
						size="sm"
						onClick={onSave}
						disabled={!name.trim() || save.isPending}
					>
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
							placeholder={
								"---\nname: my-skill\ndescription: what it does\n---\n\nInstructions…"
							}
						/>
					</div>
					<p className="text-xs text-muted-foreground">
						{t(
							"skills.createHint",
							"Add helper files (scripts/, references/, …) after saving — or import a .zip.",
						)}
					</p>
					{err && <p className="text-xs text-destructive">{err}</p>}
				</div>
			</div>
		</div>
	);
}
