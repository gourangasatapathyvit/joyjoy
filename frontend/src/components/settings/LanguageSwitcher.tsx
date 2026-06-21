import { useTranslation } from "react-i18next";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { setLanguage } from "@/i18n/config";
import { LANGUAGES } from "@/i18n/languages";

// UI-language picker (Settings → Appearance). Persists via setLanguage; every
// component using useTranslation re-renders with the new locale.
export function LanguageSwitcher() {
	const { i18n } = useTranslation();
	return (
		<Select value={i18n.language} onValueChange={(v) => v && setLanguage(v)}>
			<SelectTrigger className="w-full">
				<SelectValue />
			</SelectTrigger>
			<SelectContent>
				{LANGUAGES.map((l) => (
					<SelectItem key={l.code} value={l.code}>
						{l.endonym}
					</SelectItem>
				))}
			</SelectContent>
		</Select>
	);
}
