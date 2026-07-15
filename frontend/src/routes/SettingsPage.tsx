import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMe } from "@/api/auth";
import { ModelPicker } from "@/components/chat/ModelPicker";
import { ScrollArea } from "@/components/ui/scroll-area";
import { STORAGE_KEYS } from "@/lib/constants";
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

// Per-user (keyed by username — /v1/auth/me carries no other stable id
// client-side) so different accounts on the same browser don't inherit each
// other's last-open tab. A genuinely fresh visit (no persisted section for
// this user) lands on the first tab; any later visit restores whichever tab
// that same user had open last.
const sectionKeyFor = (username: string) =>
	`${STORAGE_KEYS.settingsSection}:${username}`;

const readSection = (username: string): Section => {
	try {
		const v = localStorage.getItem(sectionKeyFor(username));
		if ((SECTIONS as string[]).includes(v ?? "")) return v as Section;
	} catch {
		// localStorage unavailable — fall through to the default
	}
	return SECTIONS[0];
};

// Settings = webui-style side-menu (Conversation / Appearance / Providers / Profile).
export function SettingsPage() {
	const { t } = useTranslation();
	const { data: me } = useMe();
	const [section, setSectionState] = useState<Section>(SECTIONS[0]);
	// Re-hydrate once we know WHICH user this is (usually already cached/
	// synchronous by the time this route renders, since RequireAuth fetches it
	// first — but guard with a ref so a later cache refetch of the same user
	// doesn't clobber a tab switch the user already made this session).
	const hydratedFor = useRef<string | null>(null);
	useEffect(() => {
		const uid = me?.username;
		if (!uid || hydratedFor.current === uid) return;
		hydratedFor.current = uid;
		setSectionState(readSection(uid));
	}, [me?.username]);

	const setSection = (s: Section) => {
		setSectionState(s);
		if (!me?.username) return;
		try {
			localStorage.setItem(sectionKeyFor(me.username), s);
		} catch {
			// localStorage unavailable — keep in-memory only
		}
	};

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
						<div className="flex min-h-0 flex-1 flex-col">
							<ProvidersPanel />
						</div>
					</div>
				) : (
					<ScrollArea className="min-h-0 flex-1">
						<div className="p-6">
							{section === "conversation" ? (
								<ConversationPane />
							) : section === "profile" ? (
								<ProfilePane />
							) : (
								<AppearancePane />
							)}
						</div>
					</ScrollArea>
				)}
			</main>
		</div>
	);
}
