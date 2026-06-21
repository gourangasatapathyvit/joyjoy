import { create } from "zustand";

// Appearance/UX preferences (theme itself is handled by next-themes). All
// persisted to localStorage; skin is applied as a `data-skin` attr on <html>
// which the CSS in index.css maps to accent-color overrides.
// (Sidebar tab ORDER is server-backed — see api/usersettings.ts — not here.)
export type Skin = "default" | "ares" | "poseidon" | "sisyphus" | "mono";
export type ActivityDisplay = "compact" | "stream";

export const SKINS: { id: Skin; label: string; color: string }[] = [
	{ id: "default", label: "Gold", color: "#FFD700" },
	{ id: "ares", label: "Ares", color: "#FF4444" },
	{ id: "poseidon", label: "Poseidon", color: "#0EA5E9" },
	{ id: "sisyphus", label: "Sisyphus", color: "#A78BFA" },
	{ id: "mono", label: "Mono", color: "#CCCCCC" },
];

const K = {
	skin: "joyjoy-skin",
	act: "joyjoy-activity",
	follow: "joyjoy-autofollow",
};

function ls(key: string): string | null {
	try {
		return localStorage.getItem(key);
	} catch {
		return null;
	}
}
function lsSet(key: string, val: string) {
	try {
		localStorage.setItem(key, val);
	} catch {
		// localStorage unavailable — keep in-memory only
	}
}
function applySkin(skin: string) {
	try {
		document.documentElement.dataset.skin = skin;
	} catch {
		// no document (SSR/tests)
	}
}

// Apply the persisted skin immediately on module load (before first paint).
applySkin(ls(K.skin) || "default");

interface SettingsState {
	skin: Skin;
	activityDisplay: ActivityDisplay;
	autoFollow: boolean;
	setSkin: (s: Skin) => void;
	setActivityDisplay: (a: ActivityDisplay) => void;
	setAutoFollow: (b: boolean) => void;
}

export const useSettingsStore = create<SettingsState>((set) => ({
	skin: (ls(K.skin) as Skin) || "default",
	activityDisplay: (ls(K.act) as ActivityDisplay) || "compact",
	autoFollow: ls(K.follow) !== "0",
	setSkin: (skin) => {
		lsSet(K.skin, skin);
		applySkin(skin);
		set({ skin });
	},
	setActivityDisplay: (activityDisplay) => {
		lsSet(K.act, activityDisplay);
		set({ activityDisplay });
	},
	setAutoFollow: (autoFollow) => {
		lsSet(K.follow, autoFollow ? "1" : "0");
		set({ autoFollow });
	},
}));
