// The locales joyjoy ships with (mirrors the old webui's set). `dir` is "rtl"
// only where needed — all current locales are left-to-right. Endonyms are shown
// in the language switcher so each language names itself.
export interface Language {
	code: string;
	endonym: string;
	dir?: "ltr" | "rtl";
}

export const LANGUAGES: Language[] = [
	{ code: "en", endonym: "English" },
	{ code: "zh", endonym: "简体中文" },
	{ code: "zh-hant", endonym: "繁體中文" },
	{ code: "ja", endonym: "日本語" },
	{ code: "ko", endonym: "한국어" },
	{ code: "de", endonym: "Deutsch" },
	{ code: "es", endonym: "Español" },
	{ code: "fr", endonym: "Français" },
	{ code: "it", endonym: "Italiano" },
	{ code: "pt", endonym: "Português" },
	{ code: "ru", endonym: "Русский" },
	{ code: "uk", endonym: "Українська" },
	{ code: "tr", endonym: "Türkçe" },
	{ code: "hu", endonym: "Magyar" },
	{ code: "af", endonym: "Afrikaans" },
	{ code: "ga", endonym: "Gaeilge" },
];

export const LANGUAGE_CODES = LANGUAGES.map((l) => l.code);
export const DEFAULT_LANGUAGE = "en";
