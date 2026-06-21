import { create } from "zustand";

// Frontend dev-auth. The backend has no login endpoint — the Vite proxy injects a
// fixed X-User-Id (`alice`) — so this is a client-side gate + credential store:
// it guards the app routes (RequireAuth) and powers the Profile tab's password
// reset / logout. A single dev account is seeded into localStorage on first load;
// sign-in validates against it and stores a session token, logout clears it. The
// username stays `alice` to match the identity the dev proxy forwards.
interface Account {
	username: string;
	password: string;
}

const TOKEN_KEY = "joyjoy-auth-token";
const ACCT_KEY = "joyjoy-account";
const DEFAULT_ACCOUNT: Account = { username: "alice", password: "alice" };

function lsGet(k: string): string | null {
	try {
		return localStorage.getItem(k);
	} catch {
		return null;
	}
}
function lsSet(k: string, v: string) {
	try {
		localStorage.setItem(k, v);
	} catch {
		// localStorage unavailable — keep in-memory only
	}
}
function lsDel(k: string) {
	try {
		localStorage.removeItem(k);
	} catch {
		// localStorage unavailable
	}
}

// Mirror the signed-in identity into a `joyjoy_uid` cookie. When FastAPI serves
// the SPA itself (single-server), there's no proxy injecting X-User-Id and the
// SSE EventSource can't send headers — the backend reads this cookie instead
// (sent automatically on same-origin requests). In dev the Vite proxy's
// X-User-Id header still takes priority, so this is harmless there.
function setUidCookie(uid: string | null) {
	try {
		// biome-ignore lint/suspicious/noDocumentCookie: document.cookie is the portable, widely-supported way to set this identity cookie
		document.cookie = uid
			? `joyjoy_uid=${encodeURIComponent(uid)}; path=/; SameSite=Lax; max-age=31536000`
			: "joyjoy_uid=; path=/; max-age=0";
	} catch {
		// document unavailable (SSR/tests)
	}
}

// The stored account, seeding the dev default on first load so sign-in is testable.
function readAccount(): Account {
	const raw = lsGet(ACCT_KEY);
	if (raw) {
		try {
			const a = JSON.parse(raw) as Account;
			if (a?.username && typeof a.password === "string") return a;
		} catch {
			// fall through to seed the default
		}
	}
	lsSet(ACCT_KEY, JSON.stringify(DEFAULT_ACCOUNT));
	return DEFAULT_ACCOUNT;
}

interface AuthState {
	token: string | null;
	username: string | null;
	isAuthenticated: boolean;
	signIn: (
		username: string,
		password: string,
	) => { ok: boolean; error?: string };
	signOut: () => void;
	resetPassword: (
		current: string,
		next: string,
	) => { ok: boolean; error?: string };
}

export const useAuthStore = create<AuthState>((set) => {
	const account = readAccount();
	const token = lsGet(TOKEN_KEY);
	// Already signed in (persisted token) → restore the identity cookie too.
	if (token) setUidCookie(account.username);
	return {
		token,
		username: token ? account.username : null,
		isAuthenticated: !!token,
		signIn: (username, password) => {
			const a = readAccount();
			if (
				username.trim().toLowerCase() !== a.username.toLowerCase() ||
				password !== a.password
			) {
				return { ok: false, error: "Invalid username or password." };
			}
			const t = `dev-${crypto.randomUUID()}`;
			lsSet(TOKEN_KEY, t);
			setUidCookie(a.username);
			set({ token: t, username: a.username, isAuthenticated: true });
			return { ok: true };
		},
		signOut: () => {
			lsDel(TOKEN_KEY);
			setUidCookie(null);
			set({ token: null, username: null, isAuthenticated: false });
		},
		resetPassword: (current, next) => {
			const a = readAccount();
			if (current !== a.password) {
				return { ok: false, error: "Current password is incorrect." };
			}
			if (!next) return { ok: false, error: "New password cannot be empty." };
			lsSet(ACCT_KEY, JSON.stringify({ ...a, password: next }));
			return { ok: true };
		},
	};
});
