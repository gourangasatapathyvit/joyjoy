import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev-only proxy. The SPA talks to the backend /v1 directly; in production one
// FastAPI process serves this built SPA + /v1 on a single origin (no proxy, no
// webui tier — see backend app/main.py "Serve the built React SPA"). The webui
// (:8788) and its /api surface are retired (Phase 4).
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
			// Dev convenience: forward /v1 → backend :8080 and inject a dev identity
			// (X-User-Id) so you don't have to sign in to hit the API while iterating.
			// EventSource can't set headers, so doing it here also covers the SSE
			// stream. In single-server mode identity comes from the joyjoy_uid cookie.
			"/v1": {
				target: "http://127.0.0.1:8080",
				changeOrigin: true,
				configure: (proxy) => {
					proxy.on("proxyReq", (proxyReq) => {
						proxyReq.setHeader("x-user-id", "alice");
					});
				},
			},
		},
	},
});
