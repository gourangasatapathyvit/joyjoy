import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useTranslation } from "react-i18next";
import { persistPref } from "@/api/prefs";
import { useSkins } from "@/api/usersettings";
import { LanguageSwitcher } from "@/components/settings/LanguageSwitcher";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import {
	type ActivityDisplay,
	SKINS,
	type Skin,
	useSettingsStore,
} from "@/store/settings";
import { Field } from "./Field";

export function AppearancePane() {
	const { t } = useTranslation();
	const { theme, setTheme } = useTheme();
	const { data: skinData } = useSkins();
	const skins = skinData?.skins ?? SKINS;
	const skin = useSettingsStore((s) => s.skin);
	const setSkin = useSettingsStore((s) => s.setSkin);
	const activityDisplay = useSettingsStore((s) => s.activityDisplay);
	const setActivityDisplay = useSettingsStore((s) => s.setActivityDisplay);
	const autoFollow = useSettingsStore((s) => s.autoFollow);
	const setAutoFollow = useSettingsStore((s) => s.setAutoFollow);

	const themes = [
		{ id: "light", label: t("appearance.light"), icon: Sun },
		{ id: "dark", label: t("appearance.dark"), icon: Moon },
		{ id: "system", label: t("appearance.system"), icon: Monitor },
	];
	const activityModes: { id: ActivityDisplay; label: string }[] = [
		{ id: "compact", label: t("appearance.compact") },
		{ id: "stream", label: t("appearance.stream") },
	];

	return (
		<div className="mx-auto max-w-2xl space-y-4">
			<div>
				<h1 className="font-heading text-lg font-semibold text-foreground">
					{t("settings.appearance")}
				</h1>
				<p className="text-xs text-muted-foreground">
					{t("appearance.subtitle")}
				</p>
			</div>

			<Field label={t("appearance.theme")}>
				<div className="grid grid-cols-3 gap-2">
					{themes.map((opt) => (
						<button
							key={opt.id}
							type="button"
							onClick={() => {
								setTheme(opt.id);
								persistPref({ theme: opt.id });
							}}
							className={cn(
								"flex items-center justify-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors",
								theme === opt.id
									? "border-primary bg-primary/10 text-primary"
									: "border-border hover:bg-foreground/5",
							)}
						>
							<opt.icon className="size-4" /> {opt.label}
						</button>
					))}
				</div>
			</Field>

			<Field label={t("appearance.skin")} desc={t("appearance.skinDesc")}>
				<div className="flex flex-wrap gap-2">
					{skins.map((s) => (
						<button
							key={s.id}
							type="button"
							onClick={() => setSkin(s.id as Skin)}
							className={cn(
								"flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition-colors",
								skin === s.id
									? "border-primary bg-primary/10 text-foreground"
									: "border-border text-muted-foreground hover:bg-foreground/5",
							)}
						>
							<span
								className="size-3.5 rounded-full ring-1 ring-border"
								style={{ backgroundColor: s.color }}
							/>
							{s.label}
						</button>
					))}
				</div>
			</Field>

			<Field label={t("language.label")}>
				<LanguageSwitcher />
			</Field>

			<Field
				label={t("appearance.activity")}
				desc={t("appearance.activityDesc")}
			>
				<div className="grid grid-cols-2 gap-2">
					{activityModes.map((m) => (
						<button
							key={m.id}
							type="button"
							onClick={() => setActivityDisplay(m.id)}
							className={cn(
								"rounded-lg border px-3 py-2 text-sm transition-colors",
								activityDisplay === m.id
									? "border-primary bg-primary/10 text-primary"
									: "border-border hover:bg-foreground/5",
							)}
						>
							{m.label}
						</button>
					))}
				</div>
			</Field>

			<Field
				label={t("appearance.autoFollow")}
				desc={t("appearance.autoFollowDesc")}
			>
				<div className="flex items-center justify-between">
					<span className="text-sm text-foreground">
						{autoFollow
							? t("appearance.autoFollowOn")
							: t("appearance.autoFollowOff")}
					</span>
					<Switch
						checked={autoFollow}
						onCheckedChange={setAutoFollow}
						aria-label={t("appearance.autoFollow")}
					/>
				</div>
			</Field>

			<Field
				label={t("appearance.sidebarTabs")}
				desc={t("appearance.sidebarTabsDesc")}
			>
				<p className="text-sm text-muted-foreground">
					{t("appearance.sidebarTabsHint")}
				</p>
			</Field>
		</div>
	);
}
