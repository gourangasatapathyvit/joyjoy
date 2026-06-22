import { useQueryClient } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { authApi, useMe } from "@/api/auth";
import { useUiSettings, useUpdateUiSettings } from "@/api/usersettings";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Field } from "./Field";

// Profile = account identity (display name + email persisted to the backend),
// password reset, and logout. Username is read-only (it's the backend identity).
export function ProfilePane() {
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
