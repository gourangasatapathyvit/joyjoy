// Small, generic text / file helpers shared across the app. Previously these
// lived inline in whichever component first needed them (baseName in a memory
// component, parseLines/parseKV in McpPanel, fileToBase64 in ImportZipButton,
// downloadFile in ConversationPane) — centralized here so they're reused, not
// re-implemented.

/** Strip a single leading slash for display: `/a/b.txt` -> `a/b.txt`. */
export const stripLeadingSlash = (p: string): string => p.replace(/^\//, "");

/** The final path component: `/a/b.txt` -> `b.txt` (handles `\` and `/`). */
export const baseName = (p: string): string =>
	p
		.replace(/[\\/]+$/, "")
		.split(/[\\/]/)
		.pop() || p;

/** Non-empty, trimmed lines (e.g. an args textarea -> string[]). */
export const parseLines = (t: string): string[] =>
	t
		.split("\n")
		.map((s) => s.trim())
		.filter(Boolean);

/** Parse `KEY=value` lines (env / headers textareas) into an object. */
export const parseKV = (t: string): Record<string, string> => {
	const out: Record<string, string> = {};
	for (const line of t.split("\n")) {
		const i = line.indexOf("=");
		if (i > 0) out[line.slice(0, i).trim()] = line.slice(i + 1).trim();
	}
	return out;
};

/** Read a File into a base64 string (for JSON upload endpoints). */
export async function fileToBase64(file: File): Promise<string> {
	const bytes = new Uint8Array(await file.arrayBuffer());
	let bin = "";
	for (let i = 0; i < bytes.length; i += 0x8000) {
		bin += String.fromCharCode(...Array.from(bytes.subarray(i, i + 0x8000)));
	}
	return btoa(bin);
}

/** Trigger a browser download of in-memory content. */
export function downloadFile(
	name: string,
	content: string,
	type: string,
): void {
	const blob = new Blob([content], { type });
	const url = URL.createObjectURL(blob);
	const a = document.createElement("a");
	a.href = url;
	a.download = name;
	a.click();
	URL.revokeObjectURL(url);
}
