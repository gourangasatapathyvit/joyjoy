import { useQueryClient } from "@tanstack/react-query";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { authApi } from "@/api/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type Mode = "signin" | "signup" | "forgot" | "reset";

export function AuthPage() {
	const { t } = useTranslation();
	const qc = useQueryClient();
	const navigate = useNavigate();
	const location = useLocation();
	const from =
		(location.state as { from?: { pathname?: string } } | null)?.from
			?.pathname ?? "/";

	const [mode, setMode] = useState<Mode>("signin");
	const [username, setUsername] = useState("");
	const [email, setEmail] = useState("");
	const [password, setPassword] = useState("");
	const [confirm, setConfirm] = useState("");
	const [otp, setOtp] = useState("");
	const [error, setError] = useState<string | null>(null);
	const [info, setInfo] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);
	const [usernameTaken, setUsernameTaken] = useState(false);

	const switchMode = (m: Mode) => {
		setMode(m);
		setError(null);
		setInfo(null);
		setConfirm("");
		setOtp("");
	};

	// On success the backend set the session cookie; refresh `me` then continue.
	const finishAuthed = async () => {
		await qc.invalidateQueries({ queryKey: ["me"] });
		navigate(from, { replace: true });
	};

	// Live "username taken" check while signing up (debounced).
	useEffect(() => {
		if (mode !== "signup") return;
		const u = username.trim();
		if (u.length < 3) {
			setUsernameTaken(false);
			return;
		}
		const id = setTimeout(async () => {
			const res = await authApi.available(u);
			setUsernameTaken(Boolean(res.username_taken));
		}, 400);
		return () => clearTimeout(id);
	}, [username, mode]);

	const onSubmit = async (e: FormEvent) => {
		e.preventDefault();
		setError(null);
		setInfo(null);
		setBusy(true);
		try {
			if (mode === "signin") {
				const r = await authApi.login(username, password);
				if (r.ok) return await finishAuthed();
				setError(r.error ?? t("auth.signinFailed"));
			} else if (mode === "signup") {
				if (password.length < 8) return setError(t("auth.pwTooShort"));
				if (password !== confirm) return setError(t("auth.pwMismatch"));
				const r = await authApi.signup(username, email, password);
				if (r.ok) return await finishAuthed();
				setError(r.error ?? t("auth.createFailed"));
			} else if (mode === "forgot") {
				const r = await authApi.forgot(email);
				// Always succeeds (never reveals whether the email exists).
				switchMode("reset");
				setInfo(
					r.dev_otp
						? t("auth.devCode", { code: r.dev_otp })
						: t("auth.resetSent"),
				);
				if (r.dev_otp) setOtp(r.dev_otp);
			} else {
				if (password.length < 8) return setError(t("auth.pwTooShort"));
				if (password !== confirm) return setError(t("auth.pwMismatch"));
				const r = await authApi.reset(email, otp.trim(), password);
				if (r.ok) return await finishAuthed();
				setError(r.error ?? t("auth.resetFailed"));
			}
		} finally {
			setBusy(false);
		}
	};

	const title = t(`auth.${mode}Title`);
	const subtitle = t(`auth.${mode}Subtitle`);
	const linkCls = "text-primary hover:underline";

	return (
		<div className="flex min-h-svh items-center justify-center bg-background p-6 text-foreground">
			<form
				onSubmit={onSubmit}
				className="w-full max-w-sm space-y-4 rounded-2xl border border-border bg-sidebar p-8 shadow-lg"
			>
				<div className="flex flex-col items-center gap-2 text-center">
					<img src="/joyjoy-icon.svg" alt="joyjoy" className="size-12" />
					{/* brand name, not translated */}
					<h1 className="font-heading text-xl font-semibold">{title}</h1>
					<p className="text-xs text-muted-foreground">{subtitle}</p>
				</div>

				{/* Username — signin + signup */}
				{(mode === "signin" || mode === "signup") && (
					<div className="space-y-1.5">
						<Label htmlFor="username">{t("auth.username")}</Label>
						<Input
							id="username"
							value={username}
							onChange={(e) => setUsername(e.target.value)}
							autoComplete="username"
							placeholder={t("auth.usernamePlaceholder")}
							autoFocus
						/>
						{mode === "signup" && usernameTaken && (
							<p className="text-xs text-destructive">
								{t("auth.usernameTaken")}
							</p>
						)}
					</div>
				)}

				{/* Email — signup + forgot + reset */}
				{(mode === "signup" || mode === "forgot" || mode === "reset") && (
					<div className="space-y-1.5">
						<Label htmlFor="email">{t("auth.email")}</Label>
						<Input
							id="email"
							type="email"
							value={email}
							onChange={(e) => setEmail(e.target.value)}
							autoComplete="email"
							placeholder={t("auth.emailPlaceholder")}
							disabled={mode === "reset"}
							autoFocus={mode === "forgot"}
						/>
					</div>
				)}

				{/* OTP — reset */}
				{mode === "reset" && (
					<div className="space-y-1.5">
						<Label htmlFor="otp">{t("auth.resetCode")}</Label>
						<Input
							id="otp"
							value={otp}
							onChange={(e) => setOtp(e.target.value)}
							inputMode="numeric"
							placeholder={t("auth.resetCodePlaceholder")}
							autoComplete="one-time-code"
						/>
					</div>
				)}

				{/* Password — signin + signup + reset */}
				{(mode === "signin" || mode === "signup" || mode === "reset") && (
					<div className="space-y-1.5">
						<Label htmlFor="password">
							{mode === "signin" ? t("auth.password") : t("auth.newPassword")}
						</Label>
						<Input
							id="password"
							type="password"
							value={password}
							onChange={(e) => setPassword(e.target.value)}
							autoComplete={
								mode === "signin" ? "current-password" : "new-password"
							}
							placeholder={
								mode === "signin"
									? t("auth.passwordPlaceholder")
									: t("auth.newPasswordPlaceholder")
							}
						/>
					</div>
				)}

				{/* Confirm — signup + reset */}
				{(mode === "signup" || mode === "reset") && (
					<div className="space-y-1.5">
						<Label htmlFor="confirm">{t("auth.confirmPassword")}</Label>
						<Input
							id="confirm"
							type="password"
							value={confirm}
							onChange={(e) => setConfirm(e.target.value)}
							autoComplete="new-password"
						/>
					</div>
				)}

				{error && <p className="text-xs text-destructive">{error}</p>}
				{info && <p className="text-xs text-muted-foreground">{info}</p>}

				<Button type="submit" className="w-full" disabled={busy}>
					{busy
						? t("auth.pleaseWait")
						: mode === "signin"
							? t("auth.signinSubmit")
							: mode === "signup"
								? t("auth.signupSubmit")
								: mode === "forgot"
									? t("auth.forgotSubmit")
									: t("auth.resetSubmit")}
				</Button>

				{/* Mode switches */}
				<div className="space-y-1 text-center text-xs text-muted-foreground">
					{mode === "signin" && (
						<>
							<p>
								<button
									type="button"
									className={linkCls}
									onClick={() => switchMode("forgot")}
								>
									{t("auth.forgotLink")}
								</button>
							</p>
							<p>
								{t("auth.newHere")}{" "}
								<button
									type="button"
									className={linkCls}
									onClick={() => switchMode("signup")}
								>
									{t("auth.createAccount")}
								</button>
							</p>
						</>
					)}
					{mode === "signup" && (
						<p>
							{t("auth.haveAccount")}{" "}
							<button
								type="button"
								className={linkCls}
								onClick={() => switchMode("signin")}
							>
								{t("auth.signinSubmit")}
							</button>
						</p>
					)}
					{(mode === "forgot" || mode === "reset") && (
						<p>
							<button
								type="button"
								className={cn(linkCls)}
								onClick={() => switchMode("signin")}
							>
								{t("auth.backToSignin")}
							</button>
							{mode === "reset" && (
								<>
									{"  ·  "}
									<button
										type="button"
										className={linkCls}
										onClick={() => switchMode("forgot")}
									>
										{t("auth.resend")}
									</button>
								</>
							)}
						</p>
					)}
				</div>
			</form>
		</div>
	);
}
