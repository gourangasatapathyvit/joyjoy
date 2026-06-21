// ─────────────────────────────────────────────────────────────────────────
// Single API surface. Phase 1+ talks to the backend /v1 directly (the Phase 4
// target): the Vite dev proxy forwards /v1 → :8080 and injects the gateway key
// + X-User-Id, so the browser needs no session/CSRF. Keeping every call behind
// this module means production wiring is a one-file change.
// ─────────────────────────────────────────────────────────────────────────

import type { CreateRunRequest, CreateRunResponse } from "@/api/types";

export async function http<T>(path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(path, {
		credentials: "include",
		...init,
		headers: {
			"Content-Type": "application/json",
			...(init?.headers ?? {}),
		},
	});
	if (!res.ok) {
		throw new Error(`${res.status} ${res.statusText} — ${path}`);
	}
	const contentType = res.headers.get("content-type") ?? "";
	return (
		contentType.includes("application/json") ? res.json() : res.text()
	) as Promise<T>;
}

// Start a run. Returns the run_id used to open the SSE event stream.
export function createRun(body: CreateRunRequest): Promise<CreateRunResponse> {
	return http<CreateRunResponse>("/v1/runs", {
		method: "POST",
		body: JSON.stringify(body),
	});
}

// SSE endpoint for a run's events (consumed via EventSource; the proxy injects auth).
export function runEventsUrl(runId: string): string {
	return `/v1/runs/${encodeURIComponent(runId)}/events`;
}

// Cancel an in-flight run (wires the "Stop generating" button).
export function cancelRun(runId: string): Promise<{ ok: boolean }> {
	return http<{ ok: boolean }>(`/v1/runs/${encodeURIComponent(runId)}/cancel`, {
		method: "POST",
	});
}

// Respond to a HITL approval request mid-run (resumes the interrupted graph).
export function respondApproval(
	runId: string,
	approvalId: string,
	decision: "approve" | "reject",
): Promise<{ ok: boolean }> {
	return http<{ ok: boolean }>(
		`/v1/runs/${encodeURIComponent(runId)}/approvals/${encodeURIComponent(approvalId)}/respond`,
		{ method: "POST", body: JSON.stringify({ decision }) },
	);
}
