import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ModelPicker } from "@/components/chat/ModelPicker";
import { cn } from "@/lib/utils";
import { ProvidersPanel } from "@/routes/ProvidersPanel";
import { AppearancePane } from "@/routes/settings/AppearancePane";
import { ConversationPane } from "@/routes/settings/ConversationPane";
import { ProfilePane } from "@/routes/settings/ProfilePane";

type Section = "conversation" | "appearance" | "providers" | "profile";

// Labels render via t(`settings.${id}`); the array is just the ordered ids.
const SECTIONS: Section[] = [
	"conversation",
	"appearance",
	"providers",
	"profile",
];

// Settings = webui-style side-menu (Conversation / Appearance / Providers / Profile).
export function SettingsPage() {
	const { t } = useTranslation();
	const [section, setSection] = useState<Section>("appearance");

	return (
		<div className="flex min-h-0 flex-1">
			<aside className="flex w-56 shrink-0 flex-col gap-0.5 border-r border-border bg-sidebar p-2">
				<div className="px-2 py-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
					{t("settings.title")}
				</div>
				{SECTIONS.map((s) => (
					<button
						key={s}
						type="button"
						onClick={() => setSection(s)}
						className={cn(
							"rounded-md px-3 py-2 text-left text-sm transition-colors",
							section === s
								? "bg-primary/10 text-primary"
								: "text-muted-foreground hover:bg-foreground/5 hover:text-foreground",
						)}
					>
						{t(`settings.${s}`)}
					</button>
				))}
			</aside>
			<main className="flex min-h-0 flex-1 flex-col">
				{section === "providers" ? (
					<div className="flex min-h-0 flex-1 flex-col">
						<div className="border-b border-border px-6 py-3">
							<div className="mb-2 text-xs font-medium text-muted-foreground">
								{t("providers.defaultModel")}
							</div>
							<ModelPicker />
						</div>
						<div className="min-h-0 flex-1">
							<ProvidersPanel />
						</div>
					</div>
				) : (
					<div className="min-h-0 flex-1 overflow-y-auto p-6">
						{section === "conversation" ? (
							<ConversationPane />
						) : section === "profile" ? (
							<ProfilePane />
						) : (
							<AppearancePane />
						)}
					</div>
				)}
			</main>
		</div>
	);
}
