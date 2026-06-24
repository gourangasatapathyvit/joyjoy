import {
	ChevronLeft,
	ChevronRight,
	Download,
	File,
	FilePlus,
	Folder,
	FolderPlus,
	Pencil,
	RefreshCw,
	Trash2,
	Upload,
	X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { WorkspaceNode } from "@/api/types";
import {
	useWorkspaceFile,
	useWorkspaceMutations,
	useWorkspaceTree,
	workspaceApi,
} from "@/api/workspace";
import {
	formatSize,
	isImageFile,
	isMarkdownFile,
	isPdfFile,
} from "@/lib/media";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/store/chat";

function parentOf(path: string): string {
	return path.includes("/") ? path.slice(0, path.lastIndexOf("/") + 1) : "";
}

// Draggable divider on the dock's left edge: drag left to expand, right to
// collapse. Width is clamped + persisted in the chat store. Pointer capture keeps
// the drag alive even when the cursor passes over an embedded iframe (PDF view).
function ResizeHandle() {
	const setWorkspaceWidth = useChatStore((s) => s.setWorkspaceWidth);
	const [dragging, setDragging] = useState(false);

	const onPointerDown = (e: React.PointerEvent) => {
		e.preventDefault();
		(e.target as HTMLElement).setPointerCapture(e.pointerId);
		setDragging(true);
	};
	const onPointerMove = (e: React.PointerEvent) => {
		if (!dragging) return;
		// Dock is flush to the viewport's right edge → width = right edge − cursor.
		setWorkspaceWidth(window.innerWidth - e.clientX);
	};
	const stop = (e: React.PointerEvent) => {
		if (!dragging) return;
		setDragging(false);
		(e.target as HTMLElement).releasePointerCapture?.(e.pointerId);
	};

	return (
		<button
			type="button"
			aria-label="Resize workspace panel"
			tabIndex={-1}
			onPointerDown={onPointerDown}
			onPointerMove={onPointerMove}
			onPointerUp={stop}
			onPointerCancel={stop}
			className={cn(
				"absolute left-0 top-0 z-10 h-full w-2 -translate-x-1/2 cursor-col-resize touch-none",
				"before:absolute before:inset-y-0 before:left-1/2 before:w-px before:-translate-x-1/2 before:bg-transparent before:transition-colors",
				"hover:before:bg-primary/40",
				dragging && "before:bg-primary/60",
			)}
		/>
	);
}

interface TreeCtx {
	threadId: string;
	selected: string | null;
	onSelect: (p: string) => void;
	renaming: string | null;
	renameDraft: string;
	setRenameDraft: (s: string) => void;
	onStartRename: (p: string) => void;
	onCommitRename: (p: string) => void;
	onCancelRename: () => void;
	onDelete: (p: string) => void;
}

function TreeNode({
	node,
	depth,
	ctx,
}: {
	node: WorkspaceNode;
	depth: number;
	ctx: TreeCtx;
}) {
	const { t } = useTranslation();
	const [open, setOpen] = useState(depth < 1);
	const pad = depth * 12 + 6;
	const active = node.type === "file" && ctx.selected === node.path;

	return (
		<li>
			{ctx.renaming === node.path ? (
				<div
					className="flex items-center px-1 py-0.5"
					style={{ paddingLeft: pad }}
				>
					<input
						ref={(el) => el?.focus()}
						value={ctx.renameDraft}
						onChange={(e) => ctx.setRenameDraft(e.target.value)}
						onKeyDown={(e) => {
							if (e.key === "Enter") ctx.onCommitRename(node.path);
							if (e.key === "Escape") ctx.onCancelRename();
						}}
						onBlur={() => ctx.onCommitRename(node.path)}
						className="min-w-0 flex-1 rounded border border-border bg-background px-1.5 py-0.5 text-[13px] outline-none focus:border-primary focus:ring-[2px] focus:ring-primary/15"
					/>
				</div>
			) : (
				<div
					className={cn(
						"group flex items-center gap-1 rounded-md pr-1 text-[13px] transition-colors",
						active
							? "bg-primary/10 text-primary"
							: "text-foreground hover:bg-foreground/5",
					)}
				>
					<button
						type="button"
						onClick={() =>
							node.type === "dir" ? setOpen((o) => !o) : ctx.onSelect(node.path)
						}
						className={cn(
							"flex min-w-0 flex-1 items-center gap-1 py-1 text-left",
							node.type === "file" && !active && "text-muted-foreground",
						)}
						style={{ paddingLeft: node.type === "dir" ? pad : pad + 16 }}
					>
						{node.type === "dir" && (
							<ChevronRight
								className={cn(
									"size-3.5 shrink-0 text-muted-foreground transition-transform",
									open && "rotate-90",
								)}
							/>
						)}
						{node.type === "dir" ? (
							<Folder className="size-3.5 shrink-0 text-muted-foreground" />
						) : (
							<File className="size-3.5 shrink-0" />
						)}
						<span className="truncate">{node.name}</span>
					</button>
					<a
						href={workspaceApi.downloadUrl(ctx.threadId, node.path)}
						download
						onClick={(e) => e.stopPropagation()}
						title={
							node.type === "dir"
								? `${t("common.download")} (.zip)`
								: t("common.download")
						}
						className="shrink-0 text-muted-foreground opacity-0 transition-opacity hover:text-primary group-hover:opacity-100"
					>
						<Download className="size-3" />
					</a>
					<button
						type="button"
						onClick={() => ctx.onStartRename(node.path)}
						title={t("common.rename")}
						className="shrink-0 text-muted-foreground opacity-0 transition-opacity hover:text-primary group-hover:opacity-100"
					>
						<Pencil className="size-3" />
					</button>
					<button
						type="button"
						onClick={() => ctx.onDelete(node.path)}
						title={t("common.delete")}
						className="shrink-0 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
					>
						<Trash2 className="size-3" />
					</button>
				</div>
			)}
			{node.type === "dir" &&
				open &&
				node.children &&
				node.children.length > 0 && (
					<ul>
						{node.children.map((c) => (
							<TreeNode key={c.path} node={c} depth={depth + 1} ctx={ctx} />
						))}
					</ul>
				)}
		</li>
	);
}

// Format-aware viewer with inline text editing.
function FileView({
	threadId,
	path,
	onBack,
}: {
	threadId: string;
	path: string;
	onBack: () => void;
}) {
	const { t } = useTranslation();
	const name = path.split("/").pop() ?? path;
	const isImage = isImageFile(name);
	const isPdf = isPdfFile(name);
	const isMd = isMarkdownFile(name);
	const isMedia = isImage || isPdf;
	const raw = workspaceApi.rawUrl(threadId, path);

	const { data, isLoading } = useWorkspaceFile(threadId, path, !isMedia);
	const { save } = useWorkspaceMutations(threadId);
	const [editing, setEditing] = useState(false);
	const [draft, setDraft] = useState("");

	useEffect(() => {
		if (data?.content != null) setDraft(data.content);
	}, [data?.content]);

	const editable = !isMedia && data != null && !data.binary;
	const onSave = () =>
		save.mutate(
			{ path, content: draft },
			{ onSuccess: () => setEditing(false) },
		);

	return (
		<div className="flex min-h-0 flex-1 flex-col">
			<div className="flex items-center gap-2 border-b border-border px-3 py-2">
				<button
					type="button"
					onClick={onBack}
					title={t("workspace.back")}
					className="shrink-0 text-muted-foreground hover:text-foreground"
				>
					<ChevronLeft className="size-4" />
				</button>
				<span className="min-w-0 flex-1 truncate font-mono text-xs text-foreground">
					{path}
				</span>
				{isMedia ? (
					<a
						href={raw}
						target="_blank"
						rel="noreferrer"
						className="shrink-0 text-xs text-primary hover:underline"
					>
						{t("common.open")}
					</a>
				) : editable && editing ? (
					<span className="flex shrink-0 items-center gap-2">
						<button
							type="button"
							onClick={() => {
								setDraft(data?.content ?? "");
								setEditing(false);
							}}
							className="text-xs text-muted-foreground hover:text-foreground"
						>
							{t("common.cancel")}
						</button>
						<button
							type="button"
							onClick={onSave}
							disabled={save.isPending}
							className="text-xs font-medium text-primary hover:underline"
						>
							{save.isPending ? t("common.saving") : t("common.save")}
						</button>
					</span>
				) : editable ? (
					<button
						type="button"
						onClick={() => setEditing(true)}
						title={t("common.edit")}
						className="shrink-0 text-muted-foreground hover:text-primary"
					>
						<Pencil className="size-3.5" />
					</button>
				) : null}
				{data && !data.binary && !editing && (
					<span className="shrink-0 text-xs text-muted-foreground">
						{formatSize(data.size)}
					</span>
				)}
			</div>
			<div className="min-h-0 flex-1 overflow-auto">
				{isImage ? (
					<div className="flex h-full items-center justify-center p-3">
						<img
							src={raw}
							alt={name}
							className="max-h-full max-w-full object-contain"
						/>
					</div>
				) : isPdf ? (
					<iframe src={raw} title={name} className="h-full w-full border-0" />
				) : isLoading ? (
					<p className="p-3 text-xs text-muted-foreground">
						{t("common.loading")}
					</p>
				) : data?.binary ? (
					<p className="p-3 text-xs text-muted-foreground">
						Binary file ({formatSize(data.size)}) —{" "}
						<a
							href={workspaceApi.downloadUrl(threadId, path)}
							download
							className="text-primary hover:underline"
						>
							{t("common.download")}
						</a>
						.
					</p>
				) : editing ? (
					<textarea
						value={draft}
						onChange={(e) => setDraft(e.target.value)}
						className="h-full w-full resize-none bg-transparent p-3 font-mono text-xs text-foreground outline-none"
					/>
				) : isMd ? (
					<div className="markdown-body p-3">
						<ReactMarkdown remarkPlugins={[remarkGfm]}>
							{data?.content || "_(empty)_"}
						</ReactMarkdown>
					</div>
				) : (
					<pre className="whitespace-pre-wrap break-words p-3 font-mono text-xs text-foreground">
						{data?.content || "(empty)"}
					</pre>
				)}
			</div>
		</div>
	);
}

// Collapsible right-side workspace panel (webui parity): file tree + CRUD +
// format-aware viewing of the agent's per-user working dir. Lives in AppShell
// so it's reachable from every screen; toggled from the rail.
export function WorkspaceDock() {
	const { t } = useTranslation();
	const open = useChatStore((s) => s.workspaceOpen);
	const toggle = useChatStore((s) => s.toggleWorkspace);
	const threadId = useChatStore((s) => s.threadId);
	const workspaceWidth = useChatStore((s) => s.workspaceWidth);
	const { data, isLoading, refetch, isFetching } = useWorkspaceTree(threadId);
	const { save, mkdir, remove, rename, upload } =
		useWorkspaceMutations(threadId);
	const tree = data?.tree ?? [];

	const [selected, setSelected] = useState<string | null>(null);
	const [creating, setCreating] = useState<"file" | "folder" | null>(null);
	const [draftName, setDraftName] = useState("");
	const [renaming, setRenaming] = useState<string | null>(null);
	const [renameDraft, setRenameDraft] = useState("");
	const fileInputRef = useRef<HTMLInputElement>(null);

	// Switching chats → a different session workspace; clear the open file + any
	// in-progress create/rename. The tree refetches via its threadId query key.
	// biome-ignore lint/correctness/useExhaustiveDependencies: run only on session (threadId) change
	useEffect(() => {
		setSelected(null);
		setCreating(null);
		setRenaming(null);
	}, [threadId]);

	if (!open) return null;

	const commitCreate = () => {
		const nm = draftName.trim();
		setCreating(null);
		if (!nm) return;
		if (creating === "folder") mkdir.mutate(nm);
		else
			save.mutate(
				{ path: nm, content: "" },
				{ onSuccess: () => setSelected(nm) },
			);
	};
	const onUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
		const files = e.target.files;
		if (files)
			for (const f of Array.from(files)) upload.mutate({ dir: "", file: f });
		e.target.value = "";
	};
	const onDelete = (p: string) => {
		remove.mutate(p);
		if (selected === p || selected?.startsWith(`${p}/`)) setSelected(null);
	};
	const commitRename = (p: string) => {
		const nm = renameDraft.trim();
		setRenaming(null);
		if (!nm || nm === (p.split("/").pop() ?? p)) return;
		const to = parentOf(p) + nm;
		rename.mutate(
			{ from: p, to },
			{ onSuccess: () => selected === p && setSelected(to) },
		);
	};
	const ctx: TreeCtx = {
		threadId,
		selected,
		onSelect: setSelected,
		renaming,
		renameDraft,
		setRenameDraft,
		onStartRename: (p) => {
			setRenaming(p);
			setRenameDraft(p.split("/").pop() ?? p);
		},
		onCommitRename: commitRename,
		onCancelRename: () => setRenaming(null),
		onDelete,
	};

	const iconBtn =
		"inline-flex size-6 items-center justify-center rounded-md text-muted-foreground transition-colors";

	return (
		<aside
			style={{ width: workspaceWidth }}
			className="relative flex shrink-0 flex-col border-l border-border bg-sidebar"
		>
			<ResizeHandle />
			<div className="flex items-center justify-between border-b border-border px-3 py-2.5">
				<span
					title={`Session: ${threadId}`}
					className="flex cursor-help items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground"
				>
					<Folder className="size-3.5" /> {t("workspace.title")}
				</span>
				<div className="flex items-center gap-0.5">
					<button
						type="button"
						onClick={() => {
							setSelected(null);
							setCreating("file");
							setDraftName("");
						}}
						title={t("workspace.newFile")}
						className={cn(iconBtn, "hover:bg-primary/10 hover:text-primary")}
					>
						<FilePlus className="size-3.5" />
					</button>
					<button
						type="button"
						onClick={() => {
							setSelected(null);
							setCreating("folder");
							setDraftName("");
						}}
						title={t("workspace.newFolder")}
						className={cn(iconBtn, "hover:bg-primary/10 hover:text-primary")}
					>
						<FolderPlus className="size-3.5" />
					</button>
					<button
						type="button"
						onClick={() => fileInputRef.current?.click()}
						title={t("workspace.upload")}
						className={cn(iconBtn, "hover:bg-primary/10 hover:text-primary")}
					>
						<Upload className="size-3.5" />
					</button>
					<button
						type="button"
						onClick={() => refetch()}
						title={t("workspace.refresh")}
						className={cn(iconBtn, "hover:bg-primary/10 hover:text-primary")}
					>
						<RefreshCw
							className={cn("size-3.5", isFetching && "animate-spin")}
						/>
					</button>
					<button
						type="button"
						onClick={() => toggle()}
						title={t("common.close")}
						className={cn(
							iconBtn,
							"hover:bg-foreground/5 hover:text-foreground",
						)}
					>
						<X className="size-4" />
					</button>
					<input
						ref={fileInputRef}
						type="file"
						multiple
						className="hidden"
						onChange={onUpload}
					/>
				</div>
			</div>

			{selected ? (
				<FileView
					threadId={threadId}
					path={selected}
					onBack={() => setSelected(null)}
				/>
			) : (
				<div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
					{creating && (
						<div className="flex items-center gap-1 px-1 py-0.5">
							{creating === "folder" ? (
								<FolderPlus className="size-3.5 shrink-0 text-muted-foreground" />
							) : (
								<FilePlus className="size-3.5 shrink-0 text-muted-foreground" />
							)}
							<input
								ref={(el) => el?.focus()}
								value={draftName}
								onChange={(e) => setDraftName(e.target.value)}
								onKeyDown={(e) => {
									if (e.key === "Enter") commitCreate();
									if (e.key === "Escape") setCreating(null);
								}}
								onBlur={commitCreate}
								placeholder={
									creating === "folder" ? "folder name" : "file name"
								}
								className="min-w-0 flex-1 rounded border border-border bg-background px-1.5 py-0.5 text-[13px] outline-none focus:border-primary focus:ring-[2px] focus:ring-primary/15"
							/>
						</div>
					)}
					{isLoading ? (
						<p className="px-2 py-4 text-xs text-muted-foreground">
							{t("common.loading")}
						</p>
					) : tree.length === 0 && !creating ? (
						<p className="px-2 py-4 text-xs leading-relaxed text-muted-foreground">
							{t("workspace.empty")}
						</p>
					) : (
						<ul className="flex flex-col">
							{tree.map((n) => (
								<TreeNode key={n.path} node={n} depth={0} ctx={ctx} />
							))}
						</ul>
					)}
				</div>
			)}
		</aside>
	);
}
