import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { DEFAULT_LANGUAGE, LANGUAGE_CODES } from "./languages";
import { af } from "./locales/af";
import { de } from "./locales/de";
import { en } from "./locales/en";
import { es } from "./locales/es";
import { fr } from "./locales/fr";
import { ga } from "./locales/ga";
import { hu } from "./locales/hu";
import { it } from "./locales/it";
import { ja } from "./locales/ja";
import { ko } from "./locales/ko";
import { pt } from "./locales/pt";
import { ru } from "./locales/ru";
import { tr } from "./locales/tr";
import { uk } from "./locales/uk";
import { zh } from "./locales/zh";
import { zhHant } from "./locales/zh-hant";

const STORAGE_KEY = "joyjoy-locale";

// Per-locale resources. en is the source; every other file mirrors its shape and
// any gaps fall back to English (fallbackLng).
const resources = {
	en: { translation: en },
	zh: { translation: zh },
	"zh-hant": { translation: zhHant },
	ja: { translation: ja },
	ko: { translation: ko },
	de: { translation: de },
	es: { translation: es },
	fr: { translation: fr },
	it: { translation: it },
	pt: { translation: pt },
	ru: { translation: ru },
	uk: { translation: uk },
	tr: { translation: tr },
	hu: { translation: hu },
	af: { translation: af },
	ga: { translation: ga },
};

function initialLng(): string {
	try {
		const saved = localStorage.getItem(STORAGE_KEY);
		if (saved && LANGUAGE_CODES.includes(saved)) return saved;
	} catch {
		// localStorage unavailable
	}
	return DEFAULT_LANGUAGE;
}

i18n.use(initReactI18next).init({
	resources,
	lng: initialLng(),
	fallbackLng: DEFAULT_LANGUAGE,
	interpolation: { escapeValue: false },
	returnNull: false,
});

// Switch language + persist the choice (read back by initialLng on next load).
export function setLanguage(code: string): void {
	try {
		localStorage.setItem(STORAGE_KEY, code);
	} catch {
		// localStorage unavailable — in-memory switch still applies
	}
	i18n.changeLanguage(code);
}

export default i18n;
