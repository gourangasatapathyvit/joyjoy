import { useQueryClient } from "@tanstack/react-query";
import { LogOut, Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import type { ChangeEvent, ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { authApi, useMe } from "@/api/auth";
import { persistPref } from "@/api/prefs";
import { sessionApi, useSessionMutations } from "@/api/sessions";
import { useSkins, useUiSettings, useUpdateUiSettings } from "@/api/usersettings";
import { ModelPicker } from "@/components/chat/ModelPicker";
import { LanguageSwitcher } from "@/components/settings/LanguageSwitcher";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { ProvidersPanel } from "@/routes/ProvidersPanel";
import { useChatStore } from "@/store/chat";
import {
	type ActivityDisplay,
	type Skin,
	SKINS,
	useSettingsStore,
} from "@/store/settings";

type Section = "conversation" | "appearance" | "providers" | "profile";

const SECTIONS: { id: Section; label: string }[] = [
	{ id: "conversation", label: "Conversation" },
	{ id: "appearance", label: "Appearance" },
	{ id: "providers", label: "Providers" },
	{ id: "profile", label: "Profile" },
];

function downloadFile(name: string, content: string, type: string) {
	const blob = new Blob([content], { type });
	const url = URL.createObjectURL(blob);
	const a = document.createElement("a");
	a.href = url;
	a.download = name;
	a.click();
	URL.revokeObjectURL(url);
}

function Field({
	label,
	desc,
	children,
}: {
	label: string;
	desc?: string;
	children: ReactNode;
}) {
	return (
		<div className="rounded-xl border border-border bg-sidebar p-4">
			<div className="mb-2 text-xs font-medium text-muted-foreground">
				{label}
			</div>
			{children}
			{desc && <p className="mt-2 text-[11px] text-muted-foreground">{desc}</p>}
		</div>
	);
}

// Conversation = transcript/JSON export, import, and clear of the active chat.
function ConversationPane() {
	const { t } = useTranslation();
	const threadId = useChatStore((s) => s.threadId);
	const newChat = useChatStore((s) => s.newChat);
	const selectThread = useChatStore((s) => s.selectThread);
	const { remove } = useSessionMutations();
	const qc = useQueryClient();
	const fileRef = useRef<HTMLInputElement>(null);
	const [busy, setBusy] = useState(false);
	const [note, setNote] = useState<string | null>(null);

	const getMessages = async () =>
		(await sessionApi.messages(threadId)).messages ?? [];

	const onTranscript = async () => {
		setBusy(true);
		setNote(null);
		try {
			const m = await getMessages();
			const md = m.length
				? m.map((x) => `## ${x.role}\n\n${x.content || ""}`).join("\n\n")
				: "(empty conversation)";
			downloadFile(`transcript-${threadId}.md`, md, "text/markdown");
		} finally {
			setBusy(false);
		}
	};

	const onJson = async () => {
		setBusy(true);
		setNote(null);
		try {
			const m = await getMessages();
			downloadFile(
				`conversation-${threadId}.json`,
				JSON.stringify({ thread_id: threadId, messages: m }, null, 2),
				"application/json",
			);
		} finally {
			setBusy(false);
		}
	};

	const onImportFile = (e: ChangeEvent<HTMLInputElement>) => {
		const file = e.target.files?.[0];
		e.target.value = "";
		if (!file) return;
		const reader = new FileReader();
		reader.onload = async () => {
			setNote(null);
			setBusy(true);
			try {
				const parsed = JSON.parse(String(reader.result));
				const messages = Array.isArray(parsed) ? parsed : parsed.messages;
				const res = await sessionApi.importConversation(messages, parsed.title);
				if (res.thread_id) {
					qc.invalidateQueries({ queryKey: ["sessions"] });
					selectThread(res.thread_id);
					setNote(t("conversation.imported", { count: res.count ?? 0 }));
				} else {
					setNote(res.error || t("conversation.importFailed"));
				}
			} catch {
				setNote(t("conversation.readError"));
			} finally {
				setBusy(false);
			}
		};
		reader.readAsText(file);
	};

	const onClear = () => {
		remove.mutate(threadId);
		newChat();
		setNote(t("conversation.cleared"));
	};

	return (
		<div className="mx-auto max-w-2xl space-y-3">
			<div className="flex flex-wrap gap-2">
				<Button variant="outline" onClick={onTranscript} disabled={busy}>
					{t("conversation.transcript")}
				</Button>
				<Button variant="outline" onClick={onJson} disabled={busy}>
					{t("conversation.json")}
				</Button>
				<Button
					variant="outline"
					onClick={() => fileRef.current?.click()}
					disabled={busy}
				>
					{t("conversation.import")}
				</Button>
				<Button variant="outline" onClick={onClear}>
					{t("conversation.clear")}
				</Button>
				<input
					ref={fileRef}
					type="file"
					accept=".json,application/json"
					className="hidden"
					onChange={onImportFile}
				/>
			</div>
			<p className="text-[11px] text-muted-foreground">
				{t("conversation.desc")}
			</p>
			{note && <p className="text-xs text-foreground">{note}</p>}
		</div>
	);
}

function AppearancePane() {
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

// Profile = account identity (display name + email persisted to the backend),
// password reset, and logout. Username is read-only (it's the backend identity).
function ProfilePane() {
	const { t } = useTranslation();
	const { data: me } = useMe();
	const qc = useQueryClient();
	const navigate = useNavigate();
	const { data: ui } = useUiSettings();
	const update = useUpdateUiSettings();

	const [name, setName] = useState("");
	const [profileNote, setProfileNote] = useState<string | null>(null);
	const seeded = useRef(false);

	// Seed the editable display name from the server once settings load.
	useEffect(() => {
		if (!seeded.current && ui) {
			setName(ui.display_name ?? "");
			seeded.current = true;
		}
	}, [ui]);

	const [current, setCurrent] = useState("");
	const [next, setNext] = useState("");
	const [confirm, setConfirm] = useState("");
	const [pwNote, setPwNote] = useState<string | null>(null);
	const [pwBusy, setPwBusy] = useState(false);

	const saveProfile = () => {
		setProfileNote(null);
		update.mutate(
			{ display_name: name.trim() },
			{
				onSuccess: () => setProfileNote(t("profile.saved")),
				onError: () => setProfileNote(t("profile.saveError")),
			},
		);
	};

	const changePassword = async () => {
		if (next !== confirm) {
			setPwNote(t("profile.pwMismatch"));
			return;
		}
		setPwBusy(true);
		try {
			const res = await authApi.changePassword(current, next);
			setPwNote(
				res.ok
					? t("profile.pwUpdated")
					: (res.error ?? t("profile.updateFailed")),
			);
			if (res.ok) {
				setCurrent("");
				setNext("");
				setConfirm("");
			}
		} finally {
			setPwBusy(false);
		}
	};

	const onLogout = async () => {
		await authApi.logout();
		await qc.invalidateQueries({ queryKey: ["me"] });
		navigate("/signin", { replace: true });
	};

	return (
		<div className="mx-auto max-w-2xl space-y-4">
			<div>
				<h1 className="font-heading text-lg font-semibold text-foreground">
					{t("settings.profile")}
				</h1>
				<p className="text-xs text-muted-foreground">{t("profile.subtitle")}</p>
			</div>

			<Field label={t("profile.account")}>
				<div className="space-y-3">
					<div className="space-y-1.5">
						<Label htmlFor="pf-user">{t("profile.username")}</Label>
						<Input
							id="pf-user"
							value={me?.username ?? ""}
							disabled
							className="font-mono"
						/>
					</div>
					<div className="space-y-1.5">
						<Label htmlFor="pf-email">{t("profile.email")}</Label>
						<Input
							id="pf-email"
							type="email"
							value={me?.email ?? ""}
							disabled
						/>
					</div>
					<div className="space-y-1.5">
						<Label htmlFor="pf-name">{t("profile.displayName")}</Label>
						<Input
							id="pf-name"
							value={name}
							onChange={(e) => setName(e.target.value)}
							placeholder={t("profile.displayNamePlaceholder")}
						/>
					</div>
					<div className="flex items-center gap-3">
						<Button onClick={saveProfile} disabled={update.isPending}>
							{update.isPending ? t("common.saving") : t("profile.saveChanges")}
						</Button>
						{profileNote && (
							<span className="text-xs text-muted-foreground">
								{profileNote}
							</span>
						)}
					</div>
				</div>
			</Field>

			<Field
				label={t("profile.resetPassword")}
				desc={t("profile.resetPasswordDesc")}
			>
				<div className="space-y-3">
					<div className="space-y-1.5">
						<Label htmlFor="pf-cur">{t("profile.currentPassword")}</Label>
						<Input
							id="pf-cur"
							type="password"
							value={current}
							onChange={(e) => setCurrent(e.target.value)}
							autoComplete="current-password"
						/>
					</div>
					<div className="space-y-1.5">
						<Label htmlFor="pf-new">{t("profile.newPassword")}</Label>
						<Input
							id="pf-new"
							type="password"
							value={next}
							onChange={(e) => setNext(e.target.value)}
							autoComplete="new-password"
						/>
					</div>
					<div className="space-y-1.5">
						<Label htmlFor="pf-conf">{t("profile.confirmPassword")}</Label>
						<Input
							id="pf-conf"
							type="password"
							value={confirm}
							onChange={(e) => setConfirm(e.target.value)}
							autoComplete="new-password"
						/>
					</div>
					<div className="flex items-center gap-3">
						<Button
							variant="outline"
							onClick={changePassword}
							disabled={pwBusy}
						>
							{t("profile.updatePassword")}
						</Button>
						{pwNote && (
							<span className="text-xs text-muted-foreground">{pwNote}</span>
						)}
					</div>
				</div>
			</Field>

			<Field label={t("profile.session")}>
				<Button variant="destructive" onClick={onLogout}>
					<LogOut className="size-4" /> {t("profile.logout")}
				</Button>
			</Field>
		</div>
	);
}

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
						key={s.id}
						type="button"
						onClick={() => setSection(s.id)}
						className={cn(
							"rounded-md px-3 py-2 text-left text-sm transition-colors",
							section === s.id
								? "bg-primary/10 text-primary"
								: "text-muted-foreground hover:bg-foreground/5 hover:text-foreground",
						)}
					>
						{t(`settings.${s.id}`)}
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
