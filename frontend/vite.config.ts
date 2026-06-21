import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev proxy → existing joyjoy webui (:8788), which owns auth/session + CSRF,
// media, and proxies /v1 to the backend (:8080). During the migration the React
// app reuses that /api surface so auth "just works"; Phase 4 repoints straight
// at the backend and retires the webui tier.
export default defineConfig({
	plugins: [react(), tailwindcss()],
	resolve: {
		alias: {
			"@": path.resolve(import.meta.dirname, "./src"),
		},
	},
	server: {
		port: 5173,
		proxy: {
			// Phase 1+: the SPA talks to the backend /v1 directly (the Phase 4 target,
			// reached early). The backend auth is just a gateway key + X-User-Id, so the
			// proxy injects both — EventSource can't set headers, so doing it here also
			// covers the SSE event stream.
			"/v1": {
				target: "http://127.0.0.1:8080",
				changeOrigin: true,
				configure: (proxy) => {
					proxy.on("proxyReq", (proxyReq) => {
						proxyReq.setHeader("x-api-key", "dev-gateway-key-change-me");
						proxyReq.setHeader("x-user-id", "alice");
					});
				},
			},
			"/api": {
				target: "http://127.0.0.1:8788",
				changeOrigin: true,
				configure: (proxy) => {
					// joyjoy webui _check_csrf requires the request Origin to match its
					// Host. The dev server is a different origin, so rewrite Origin to
					// the proxy target; otherwise POST /api/* is rejected as cross-origin.
					proxy.on("proxyReq", (proxyReq) => {
						proxyReq.setHeader("origin", "http://127.0.0.1:8788");
					});
				},
			},
		},
	},
});
