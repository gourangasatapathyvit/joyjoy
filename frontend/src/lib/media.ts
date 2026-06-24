// Media helpers for chat rendering. Agent media comes from: absolute paths via a
// `MEDIA:<path>` line (→ /v1/media?path=), files the agent wrote into the
// per-session workspace (→ /v1/workspace/raw?thread_id&path), and base64 blocks.
// Office docs are converted to PDF server-side (?convert=pdf); text/code/markdown
// files are fetched and rendered client-side. All go through the /v1 dev proxy.

const IMAGE_EXTS = new Set([
	".png",
	".jpg",
	".jpeg",
	".gif",
	".webp",
	".bmp",
	".ico",
	".svg",
	".heic",
	".heif",
	".avif",
]);
const PDF_EXTS = new Set([".pdf"]);
const OFFICE_EXTS = new Set([
	".doc",
	".docx",
	".xls",
	".xlsx",
	".ppt",
	".pptx",
	".odt",
	".ods",
	".odp",
	".rtf",
]);
const AUDIO_EXTS = new Set([".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"]);
const VIDEO_EXTS = new Set([".mp4", ".webm", ".mov", ".m4v"]);
const AV_EXTS = new Set([...AUDIO_EXTS, ...VIDEO_EXTS]);
const MARKDOWN_EXTS = new Set([".md", ".markdown"]);
const TEXT_EXTS = new Set([
	...MARKDOWN_EXTS,
	".txt",
	".csv",
	".tsv",
	".json",
	".jsonl",
	".xml",
	".yaml",
	".yml",
	".html",
	".htm",
	".css",
	".py",
	".js",
	".ts",
	".tsx",
	".jsx",
	".mjs",
	".cjs",
	".sh",
	".bash",
	".zsh",
	".go",
	".rs",
	".java",
	".kt",
	".c",
	".cc",
	".cpp",
	".h",
	".hpp",
	".rb",
	".php",
	".sql",
	".toml",
	".ini",
	".cfg",
	".conf",
	".log",
]);
// "Media" = binary/visual artifacts worth auto-previewing when the agent WRITES
// one (write_file). Text/code/markdown are excluded here — they only render inline
// when the agent explicitly emits a MEDIA: marker (else every code file it writes
// would clutter the chat).
const MEDIA_EXTS = new Set([
	...IMAGE_EXTS,
	...PDF_EXTS,
	...OFFICE_EXTS,
	...AV_EXTS,
]);

const MIME: Record<string, string> = {
	".png": "image/png",
	".jpg": "image/jpeg",
	".jpeg": "image/jpeg",
	".gif": "image/gif",
	".webp": "image/webp",
	".svg": "image/svg+xml",
	".bmp": "image/bmp",
	".ico": "image/x-icon",
	".pdf": "application/pdf",
	".mp3": "audio/mpeg",
	".wav": "audio/wav",
	".ogg": "audio/ogg",
	".mp4": "video/mp4",
	".webm": "video/webm",
	".mov": "video/quicktime",
	".docx":
		"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
	".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
	".pptx":
		"application/vnd.openxmlformats-officedocument.presentationml.presentation",
	".doc": "application/msword",
	".xls": "application/vnd.ms-excel",
	".ppt": "application/vnd.ms-powerpoint",
	".md": "text/markdown",
	".txt": "text/plain",
	".csv": "text/csv",
	".json": "application/json",
};

export const extOf = (name: string): string => {
	const i = name.lastIndexOf(".");
	return i >= 0 ? name.slice(i).toLowerCase() : "";
};
// Human-readable byte size (B / KB / MB). Empty string for null/undefined.
export const formatSize = (bytes?: number): string => {
	if (bytes == null) return "";
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
	return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};
export const isImageFile = (name: string): boolean =>
	IMAGE_EXTS.has(extOf(name));
export const isAudioFile = (name: string): boolean =>
	AUDIO_EXTS.has(extOf(name));
export const isVideoFile = (name: string): boolean =>
	VIDEO_EXTS.has(extOf(name));
export const isPdfFile = (name: string): boolean => PDF_EXTS.has(extOf(name));
export const isOfficeFile = (name: string): boolean =>
	OFFICE_EXTS.has(extOf(name));
export const isTextFile = (name: string): boolean => TEXT_EXTS.has(extOf(name));
export const isMarkdownFile = (name: string): boolean =>
	MARKDOWN_EXTS.has(extOf(name));
// Auto-previewable media artifact (used to gate write_file previews).
export const isMediaFile = (name: string): boolean =>
	MEDIA_EXTS.has(extOf(name));
export const mimeOf = (name: string): string =>
	MIME[extOf(name)] ?? "application/octet-stream";

// True for an inline `data:` URL (already-embedded bytes — no fetch needed).
export const isDataUrl = (url: string): boolean => url.startsWith("data:");

// ── Workspace-readiness helpers (gate inline media on the file existing) ──────
// Parse a workspace-served media URL (/v1/media or /v1/workspace/raw) back into
// its {threadId, path} so the renderer can check the file against the workspace
// tree before fetching. Returns null for data:/external URLs (nothing to gate).
export function parseWorkspaceMediaUrl(
	url: string,
): { threadId: string; path: string } | null {
	if (!url || isDataUrl(url)) return null;
	const q = url.indexOf("?");
	if (q < 0) return null;
	const base = url.slice(0, q);
	if (!base.endsWith("/v1/media") && !base.endsWith("/v1/workspace/raw"))
		return null;
	const params = new URLSearchParams(url.slice(q + 1));
	const threadId = params.get("thread_id") || "";
	const path = params.get("path") || "";
	return path ? { threadId, path } : null;
}

// Map a (possibly mount-prefixed/absolute) media path to its workspace-relative
// form so it can be matched against the tree's relative node paths. Returns null
// when the path is absolute but NOT under the mount (a host/external path that
// can't live in the workspace tree — caller should not gate it).
export function relWorkspacePath(path: string, mount: string): string | null {
	const m = (mount || "/workspace").replace(/\/+$/, "");
	const raw = (path ?? "").trim();
	if (raw === m) return "";
	let p = raw;
	if (p.startsWith(`${m}/`)) p = p.slice(m.length + 1);
	else if (raw.startsWith("/")) return null; // absolute, outside the mount
	return p.replace(/^\/+/, "");
}

// Flatten a workspace tree (nested {path,type,children}) to the set of FILE paths,
// each workspace-relative (matching relWorkspacePath output).
export function flattenWorkspaceFilePaths(
	nodes: ReadonlyArray<{
		path: string;
		type: "dir" | "file";
		children?: ReadonlyArray<{
			path: string;
			type: "dir" | "file";
			children?: unknown;
		}>;
	}>,
): Set<string> {
	const out = new Set<string>();
	// biome-ignore lint/suspicious/noExplicitAny: recursive tree, shape guarded above
	const walk = (ns: ReadonlyArray<any>) => {
		for (const n of ns) {
			if (n.type === "file") out.add(String(n.path).replace(/^\/+/, ""));
			if (n.children?.length) walk(n.children);
		}
	};
	walk(nodes);
	return out;
}

// thread_id lets the backend resolve the marker inside the session's sandbox
// volume when SANDBOX_ENABLED (else it's ignored and a host path is used).
export const mediaUrl = (threadId: string, path: string): string =>
	`/v1/media?thread_id=${encodeURIComponent(threadId)}&path=${encodeURIComponent(path)}`;
export const workspaceRawUrl = (threadId: string, path: string): string =>
	`/v1/workspace/raw?thread_id=${encodeURIComponent(threadId)}&path=${encodeURIComponent(path)}`;
// Ask the server to convert an office doc to PDF for inline preview. Both source
// URLs already carry a query string, so always append with `&`.
export const asPdf = (url: string): string => `${url}&convert=pdf`;

// Whole-line `MEDIA:<path>` marker (hermes convention). Tolerates wrapping
// quotes/backticks and paths with spaces; captures the path.
const MEDIA_LINE_RE = /^[ \t]*[`"']?MEDIA:[ \t]*(.+?)[`"']?[ \t]*$/;

export type TextSegment = { kind: "text"; text: string };
export type MediaSegment = { kind: "media"; path: string };

// Split assistant text into ordered text/media segments, lifting MEDIA: lines out.
export function splitMediaMarkers(
	text: string,
): (TextSegment | MediaSegment)[] {
	if (!text.includes("MEDIA:")) return text ? [{ kind: "text", text }] : [];
	const segs: (TextSegment | MediaSegment)[] = [];
	let buf: string[] = [];
	const flush = () => {
		const joined = buf.join("\n");
		if (joined.trim()) segs.push({ kind: "text", text: joined });
		buf = [];
	};
	for (const line of text.split("\n")) {
		const m = line.match(MEDIA_LINE_RE);
		if (m) {
			flush();
			segs.push({ kind: "media", path: m[1].trim() });
		} else {
			buf.push(line);
		}
	}
	flush();
	return segs;
}
