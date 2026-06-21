import type { QueryClient } from "@tanstack/react-query";
import { http } from "@/api/client";
import type { UiSettings } from "@/api/usersettings";

// Server-side persistence for appearance/UX prefs (skin, theme, locale, activity,
// auto-follow, default model/reasoning). The zustand stores + next-themes + i18n
// stay the source of instant UI reactivity; this mirrors each change to the
// backend (UserConfig) so prefs follow the user across devices/reloads.
//
// The TanStack cache (["ui-settings"]) is kept in sync so the full-merge writers
// (Profile display-name, sidebar reorder) never clobber a value changed here.

const KEY = ["ui-settings"];
let qc: QueryClient | null = null;
let suspended = false;

export function bindPrefsClient(client: QueryClient): void {
	qc = client;
}

/** Suspend saving while applying server values on load (avoids an echo PUT). */
export function suspendPrefSave(v: boolean): void {
	suspended = v;
}

/** Persist a partial prefs change to the server (fire-and-forget) and keep the
 *  query cache current so other writers merge against fresh values. */
export function persistPref(partial: UiSettings): void {
	if (suspended || !qc) return;
	const next = { ...(qc.getQueryData<UiSettings>(KEY) ?? {}), ...partial };
	qc.setQueryData<UiSettings>(KEY, next);
	http("/v1/settings/ui", { method: "PUT", body: JSON.stringify(next) }).catch(
		() => {
			// best-effort; the local store already reflects the change
		},
	);
}
