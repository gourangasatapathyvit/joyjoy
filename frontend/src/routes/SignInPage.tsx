import type { FormEvent } from "react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/store/auth";

// Sign-in screen (public route). On success it returns the user to wherever the
// auth guard intercepted them (location.state.from), defaulting to the chat.
export function SignInPage() {
	const { t } = useTranslation();
	const signIn = useAuthStore((s) => s.signIn);
	const navigate = useNavigate();
	const location = useLocation();
	const from =
		(location.state as { from?: { pathname?: string } } | null)?.from
			?.pathname ?? "/";
	const [username, setUsername] = useState("");
	const [password, setPassword] = useState("");
	const [error, setError] = useState<string | null>(null);

	const onSubmit = (e: FormEvent) => {
		e.preventDefault();
		const res = signIn(username, password);
		if (res.ok) navigate(from, { replace: true });
		else setError(t("signin.invalid"));
	};

	return (
		<div className="flex min-h-svh items-center justify-center bg-background p-6 text-foreground">
			<form
				onSubmit={onSubmit}
				className="w-full max-w-sm space-y-5 rounded-2xl border border-border bg-sidebar p-8 shadow-lg"
			>
				<div className="flex flex-col items-center gap-2 text-center">
					<img src="/joyjoy-icon.svg" alt="joyjoy" className="size-12" />
					<h1 className="font-heading text-xl font-semibold">
						{t("signin.title")}
					</h1>
					<p className="text-xs text-muted-foreground">
						{t("signin.subtitle")}
					</p>
				</div>
				<div className="space-y-1.5">
					<Label htmlFor="username">{t("signin.username")}</Label>
					<Input
						id="username"
						value={username}
						onChange={(e) => setUsername(e.target.value)}
						autoComplete="username"
						placeholder="alice"
						autoFocus
					/>
				</div>
				<div className="space-y-1.5">
					<Label htmlFor="password">{t("signin.password")}</Label>
					<Input
						id="password"
						type="password"
						value={password}
						onChange={(e) => setPassword(e.target.value)}
						autoComplete="current-password"
						placeholder="••••"
					/>
				</div>
				{error && <p className="text-xs text-destructive">{error}</p>}
				<Button type="submit" className="w-full">
					{t("signin.submit")}
				</Button>
				<p className="text-center text-[11px] text-muted-foreground">
					{t("signin.devAccount")}{" "}
					<span className="font-mono">alice / alice</span>
				</p>
			</form>
		</div>
	);
}
