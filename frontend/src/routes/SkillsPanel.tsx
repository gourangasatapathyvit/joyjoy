import { Lock, Plus, Search, Sparkles, X } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSkillMutations, useSkills } from "@/api/queries";
import { CreateSkillForm } from "@/components/skills/CreateSkillForm";
import { ImportZipButton } from "@/components/skills/ImportZipButton";
import { SkillWorkspace } from "@/components/skills/SkillWorkspace";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

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
		? skills.filter((s) =>
				`${s.name} ${s.description ?? ""}`.toLowerCase().includes(q),
			)
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
						<p className="px-2 py-4 text-xs text-muted-foreground">
							{t("common.loading")}
						</p>
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
													onCheckedChange={(v) =>
														toggle.mutate({ name: s.name, enabled: v })
													}
													aria-label={
														s.enabled ? t("skills.disable") : t("skills.enable")
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
							<p className="text-sm font-medium text-foreground">
								{t("skills.selectTitle")}
							</p>
							<p className="mx-auto max-w-xs text-xs text-muted-foreground">
								{t("skills.selectHint")}
							</p>
						</div>
						<Button
							size="sm"
							variant="outline"
							onClick={() => setCreating(true)}
						>
							<Plus className="size-3.5" /> {t("skills.newSkill")}
						</Button>
					</div>
				)}
			</main>
		</div>
	);
}
