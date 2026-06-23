import { Brain, FileText, Plus, Search, X } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMemoryFileMutations, useMemoryFiles } from "@/api/queries";
import { AgentsEditor } from "@/components/memory/AgentsEditor";
import { FileEditor } from "@/components/memory/FileEditor";
import { NewFileForm } from "@/components/memory/NewFileForm";
import { Switch } from "@/components/ui/switch";
import { AGENTS_DOC as AGENTS, NEW_ITEM as NEW } from "@/lib/constants";
import { stripLeadingSlash } from "@/lib/text";
import { cn } from "@/lib/utils";

// Memory = master/detail (like Skills): AGENTS.md pinned on top of a searchable
// list of /memories/ files (each with an enable/disable toggle); the right pane
// views (markdown) or edits the selected item.
export function MemoryPanel() {
	const { t } = useTranslation();
	const { data } = useMemoryFiles();
	const files = data?.files ?? [];
	const { toggle } = useMemoryFileMutations();
	const [sel, setSel] = useState<string>(AGENTS);
	const [query, setQuery] = useState("");

	const q = query.trim().toLowerCase();
	const filtered = q
		? files.filter((f) => f.path.toLowerCase().includes(q))
		: files;

	return (
		<div className="flex min-h-0 flex-1">
			<aside className="flex w-[300px] shrink-0 flex-col border-r border-border bg-sidebar">
				<div className="flex items-center justify-between gap-1 px-4 py-3">
					<span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
						{t("memory.title")}
					</span>
					<button
						type="button"
						onClick={() => setSel(NEW)}
						title={t("memory.newFile")}
						className="inline-flex size-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary"
					>
						<Plus className="size-4" />
					</button>
				</div>

				<div className="relative px-3 pb-2">
					<Search className="-translate-y-1/2 pointer-events-none absolute top-1/2 left-[22px] size-3.5 text-muted-foreground opacity-70" />
					<input
						value={query}
						onChange={(e) => setQuery(e.target.value)}
						placeholder={t("memory.searchPlaceholder")}
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
					<ul className="flex flex-col gap-0.5">
						<li>
							<button
								type="button"
								onClick={() => setSel(AGENTS)}
								className={cn(
									"flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left transition-colors",
									sel === AGENTS ? "bg-primary/10" : "hover:bg-foreground/5",
								)}
							>
								<Brain
									className={cn(
										"size-4 shrink-0",
										sel === AGENTS ? "text-primary" : "text-muted-foreground",
									)}
								/>
								<span className="flex min-w-0 flex-1 flex-col">
									<span
										className={cn(
											"truncate text-[13px] font-medium",
											sel === AGENTS ? "text-primary" : "text-foreground",
										)}
									>
										AGENTS.md
									</span>
									<span className="truncate text-[11px] text-muted-foreground">
										{t("memory.coreHint")}
									</span>
								</span>
							</button>
						</li>

						<li className="px-2 pt-3 pb-1">
							<span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
								/memories/
							</span>
						</li>

						{filtered.length === 0 ? (
							<li className="px-2 py-2 text-[11px] text-muted-foreground italic">
								{q ? t("common.noMatches") : t("memory.noFiles")}
							</li>
						) : (
							filtered.map((f) => {
								const active = sel === f.path;
								return (
									<li key={f.path}>
										<div
											className={cn(
												"group flex items-center gap-2 rounded-lg px-2 py-2 transition-colors",
												active ? "bg-primary/10" : "hover:bg-foreground/5",
											)}
										>
											<button
												type="button"
												onClick={() => setSel(f.path)}
												className={cn(
													"flex min-w-0 flex-1 items-center gap-2 text-left",
													!f.enabled && "opacity-55",
												)}
											>
												<FileText
													className={cn(
														"size-4 shrink-0",
														active ? "text-primary" : "text-muted-foreground",
													)}
												/>
												<span className="flex min-w-0 flex-1 flex-col">
													<span
														className={cn(
															"truncate text-[13px] font-medium",
															active ? "text-primary" : "text-foreground",
														)}
													>
														{stripLeadingSlash(f.path)}
													</span>
													<span className="truncate text-[11px] text-muted-foreground">
														{f.size} B
													</span>
												</span>
											</button>
											<Switch
												checked={f.enabled}
												onCheckedChange={(v) =>
													toggle.mutate({ path: f.path, enabled: v })
												}
												aria-label={
													f.enabled
														? t("memory.disableFile")
														: t("memory.enableFile")
												}
												className="shrink-0"
											/>
										</div>
									</li>
								);
							})
						)}
					</ul>
				</div>
			</aside>

			<main className="flex min-h-0 flex-1 flex-col">
				{sel === NEW ? (
					<NewFileForm onSaved={setSel} onCancel={() => setSel(AGENTS)} />
				) : sel === AGENTS ? (
					<AgentsEditor />
				) : (
					<FileEditor key={sel} path={sel} onDeleted={() => setSel(AGENTS)} />
				)}
			</main>
		</div>
	);
}
