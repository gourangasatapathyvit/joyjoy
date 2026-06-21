import { useQueryClient } from "@tanstack/react-query";
import type { FormEvent } from "react";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { authApi } from "@/api/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type Mode = "signin" | "signup" | "forgot" | "reset";

const TITLES: Record<Mode, { title: string; subtitle: string }> = {
	signin: {
		title: "Sign in to joyjoy",
		subtitle: "Enter your credentials to continue.",
	},
	signup: {
		title: "Create your account",
		subtitle: "Sign up to start using joyjoy.",
	},
	forgot: {
		title: "Reset your password",
		subtitle: "We'll email you a one-time code.",
	},
	reset: {
		title: "Enter your reset code",
		subtitle: "Check your email for the 6-digit code.",
	},
};

export function AuthPage() {
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
				setError(r.error ?? "Sign-in failed.");
			} else if (mode === "signup") {
				if (password.length < 8)
					return setError("Password must be at least 8 characters.");
				if (password !== confirm) return setError("Passwords do not match.");
				const r = await authApi.signup(username, email, password);
				if (r.ok) return await finishAuthed();
				setError(r.error ?? "Could not create account.");
			} else if (mode === "forgot") {
				const r = await authApi.forgot(email);
				// Always succeeds (never reveals whether the email exists).
				switchMode("reset");
				setInfo(
					r.dev_otp
						? `Dev mode (no email configured) — your code is ${r.dev_otp}`
						: "If that email has an account, a reset code is on its way.",
				);
				if (r.dev_otp) setOtp(r.dev_otp);
			} else {
				if (password.length < 8)
					return setError("Password must be at least 8 characters.");
				if (password !== confirm) return setError("Passwords do not match.");
				const r = await authApi.reset(email, otp.trim(), password);
				if (r.ok) return await finishAuthed();
				setError(r.error ?? "Could not reset password.");
			}
		} finally {
			setBusy(false);
		}
	};

	const { title, subtitle } = TITLES[mode];
	const linkCls = "text-primary hover:underline";

	return (
		<div className="flex min-h-svh items-center justify-center bg-background p-6 text-foreground">
			<form
				onSubmit={onSubmit}
				className="w-full max-w-sm space-y-4 rounded-2xl border border-border bg-sidebar p-8 shadow-lg"
			>
				<div className="flex flex-col items-center gap-2 text-center">
					<img src="/joyjoy-icon.svg" alt="joyjoy" className="size-12" />
					<h1 className="font-heading text-xl font-semibold">{title}</h1>
					<p className="text-xs text-muted-foreground">{subtitle}</p>
				</div>

				{/* Username — signin + signup */}
				{(mode === "signin" || mode === "signup") && (
					<div className="space-y-1.5">
						<Label htmlFor="username">Username</Label>
						<Input
							id="username"
							value={username}
							onChange={(e) => setUsername(e.target.value)}
							autoComplete="username"
							placeholder="your-username"
							autoFocus
						/>
						{mode === "signup" && usernameTaken && (
							<p className="text-xs text-destructive">
								That username is already taken.
							</p>
						)}
					</div>
				)}

				{/* Email — signup + forgot + reset */}
				{(mode === "signup" || mode === "forgot" || mode === "reset") && (
					<div className="space-y-1.5">
						<Label htmlFor="email">Email</Label>
						<Input
							id="email"
							type="email"
							value={email}
							onChange={(e) => setEmail(e.target.value)}
							autoComplete="email"
							placeholder="you@example.com"
							disabled={mode === "reset"}
							autoFocus={mode === "forgot"}
						/>
					</div>
				)}

				{/* OTP — reset */}
				{mode === "reset" && (
					<div className="space-y-1.5">
						<Label htmlFor="otp">Reset code</Label>
						<Input
							id="otp"
							value={otp}
							onChange={(e) => setOtp(e.target.value)}
							inputMode="numeric"
							placeholder="6-digit code"
							autoComplete="one-time-code"
						/>
					</div>
				)}

				{/* Password — signin + signup + reset */}
				{(mode === "signin" || mode === "signup" || mode === "reset") && (
					<div className="space-y-1.5">
						<Label htmlFor="password">
							{mode === "signin" ? "Password" : "New password"}
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
								mode === "signin" ? "••••••••" : "At least 8 characters"
							}
						/>
					</div>
				)}

				{/* Confirm — signup + reset */}
				{(mode === "signup" || mode === "reset") && (
					<div className="space-y-1.5">
						<Label htmlFor="confirm">Confirm password</Label>
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
						? "Please wait…"
						: mode === "signin"
							? "Sign in"
							: mode === "signup"
								? "Create account"
								: mode === "forgot"
									? "Send reset code"
									: "Reset password"}
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
									Forgot password?
								</button>
							</p>
							<p>
								New here?{" "}
								<button
									type="button"
									className={linkCls}
									onClick={() => switchMode("signup")}
								>
									Create an account
								</button>
							</p>
						</>
					)}
					{mode === "signup" && (
						<p>
							Already have an account?{" "}
							<button
								type="button"
								className={linkCls}
								onClick={() => switchMode("signin")}
							>
								Sign in
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
								← Back to sign in
							</button>
							{mode === "reset" && (
								<>
									{"  ·  "}
									<button
										type="button"
										className={linkCls}
										onClick={() => switchMode("forgot")}
									>
										Resend code
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
