import { ChevronDown, ChevronRight, FileText, Folder, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SKILL_MANIFEST } from "@/lib/constants";
import { cn } from "@/lib/utils";

// A nested folder tree built from flat relative paths (e.g. "scripts/run.py").
export type TreeNode = {
	name: string;
	path: string;
	dir: boolean;
	children: TreeNode[];
};

export function buildTree(paths: string[]): TreeNode[] {
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
				node = {
					name: seg,
					path: isFile ? p : acc,
					dir: !isFile,
					children: [],
				};
				level.push(node);
			}
			level = node.children;
		});
	}
	const sort = (ns: TreeNode[]) => {
		ns.sort((a, b) =>
			a.dir !== b.dir ? (a.dir ? -1 : 1) : a.name.localeCompare(b.name),
		);
		for (const n of ns) sort(n.children);
	};
	sort(roots);
	roots.sort((a, b) =>
		a.name === SKILL_MANIFEST ? -1 : b.name === SKILL_MANIFEST ? 1 : 0,
	); // SKILL.md first
	return roots;
}

// Recursive tree rows: folders collapse/expand; files select; editable files get a delete.
export function FileTreeNodes({
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
	const { t } = useTranslation();
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
								<span className="truncate font-mono text-[12px] text-foreground">
									{n.name}
								</span>
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
									n.path === SKILL_MANIFEST && "font-semibold",
								)}
							>
								{n.name}
							</span>
						</button>
						{editable && n.path !== SKILL_MANIFEST && (
							<button
								type="button"
								onClick={() => onDelete(n.path)}
								title={t("common.delete")}
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
