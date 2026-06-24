// Sentinel id for the "add new" state of a master/detail panel — used as the
// selection value and as the conditionally-mounted form's remount `key` so its
// internal state resets when switching between add and edit.
export const NEW_ITEM = "__new__";

// Sentinel id for the always-loaded AGENTS.md "core memory" entry in the Memory
// panel's master/detail list (distinct from a real /memories/ file path).
export const AGENTS_DOC = "__agents__";

// localStorage keys — single source of truth so reads and writes can't drift.
// All prefixed `joyjoy-` to namespace this app's entries.
export const STORAGE_KEYS = {
	workspaceOpen: "joyjoy-workspace-open",
	workspaceWidth: "joyjoy-workspace-width",
	activeThread: "joyjoy-active-thread",
	skin: "joyjoy-skin",
	activity: "joyjoy-activity",
	autoFollow: "joyjoy-autofollow",
} as const;

// Resizable workspace dock bounds (px). The handle clamps drags to this range.
export const WORKSPACE_DOCK = {
	minWidth: 240,
	maxWidth: 720,
	defaultWidth: 360,
} as const;
