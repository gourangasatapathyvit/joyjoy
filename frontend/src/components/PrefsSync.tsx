import { useTheme } from "next-themes";
import { useEffect, useRef } from "react";
import { suspendPrefSave } from "@/api/prefs";
import { useUiSettings } from "@/api/usersettings";
import type { ReasoningEffort } from "@/api/types";
import { setLanguage } from "@/i18n/config";
import { useChatStore } from "@/store/chat";
import { type ActivityDisplay, type Skin, useSettingsStore } from "@/store/settings";

// Applies the user's server-stored prefs (UserConfig) once after login: skin,
// theme, locale, activity display, auto-follow, and the default model/reasoning.
// Saving is suspended while applying so hydration doesn't echo a PUT back.
// Renders nothing.
export function PrefsSync() {
	const { data: ui } = useUiSettings();
	const { setTheme } = useTheme();
	const applied = useRef(false);

	useEffect(() => {
		if (!ui || applied.current) return;
		applied.current = true;
		suspendPrefSave(true);
		try {
			if (ui.skin) useSettingsStore.getState().setSkin(ui.skin as Skin);
			if (ui.theme) setTheme(ui.theme);
			if (ui.locale) setLanguage(ui.locale);
			if (ui.activity_display)
				useSettingsStore
					.getState()
					.setActivityDisplay(ui.activity_display as ActivityDisplay);
			if (typeof ui.auto_follow === "boolean")
				useSettingsStore.getState().setAutoFollow(ui.auto_follow);
			if (ui.default_model) useChatStore.getState().setModel(ui.default_model);
			if (ui.default_reasoning)
				useChatStore
					.getState()
					.setReasoningEffort(ui.default_reasoning as ReasoningEffort);
		} finally {
			suspendPrefSave(false);
		}
	}, [ui, setTheme]);

	return null;
}
