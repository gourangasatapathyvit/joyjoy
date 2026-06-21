import { useQuery } from "@tanstack/react-query";

// Real auth against the backend /v1/auth/* routes. The session is an httpOnly
// cookie set by the server (JS can't read it), so the app learns its auth state
// only from GET /v1/auth/me. All requests are same-origin with credentials.

export interface Me {
	username: string;
	email?: string | null;
}

export interface AuthResult {
	ok: boolean;
	error?: string;
	field?: "username" | "email" | "password";
	user?: Me;
	dev_otp?: string; // dev-only: returned by /forgot when SMTP isn't configured
}

async function post(path: string, body: unknown): Promise<AuthResult> {
	try {
		const res = await fetch(path, {
			method: "POST",
			credentials: "include",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(body),
		});
		const data = (await res.json().catch(() => ({}))) as Partial<AuthResult>;
		return { ...data, ok: res.ok && data.ok !== false };
	} catch {
		return { ok: false, error: "Network error — is the server running?" };
	}
}

export const authApi = {
	me: async (): Promise<Me> => {
		const res = await fetch("/v1/auth/me", { credentials: "include" });
		if (!res.ok) throw new Error("unauthenticated");
		return res.json();
	},
	login: (username: string, password: string) =>
		post("/v1/auth/login", { username, password }),
	signup: (username: string, email: string, password: string) =>
		post("/v1/auth/signup", { username, email, password }),
	logout: () => post("/v1/auth/logout", {}),
	forgot: (email: string) => post("/v1/auth/forgot", { email }),
	reset: (email: string, otp: string, password: string) =>
		post("/v1/auth/reset", { email, otp, password }),
	changePassword: (current: string, next: string) =>
		post("/v1/auth/change-password", { current, new: next }),
	available: async (
		username?: string,
		email?: string,
	): Promise<{ username_taken?: boolean; email_taken?: boolean }> => {
		const q = new URLSearchParams();
		if (username) q.set("username", username);
		if (email) q.set("email", email);
		const res = await fetch(`/v1/auth/available?${q.toString()}`, {
			credentials: "include",
		});
		return res.ok ? res.json() : {};
	},
};

// Current user (drives the RequireAuth gate). 401 → throws → isError.
export function useMe() {
	return useQuery({
		queryKey: ["me"],
		queryFn: authApi.me,
		retry: false,
		staleTime: 60_000,
	});
}
