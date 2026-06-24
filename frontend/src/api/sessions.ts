import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { http } from "@/api/client";
import type { Ok, Session, SessionMessageWire } from "@/api/types";

export const sessionApi = {
	list: () => http<{ sessions: Session[] }>("/v1/sessions"),
	messages: (tid: string) =>
		http<{ thread_id: string; messages: SessionMessageWire[] }>(
			`/v1/sessions/${encodeURIComponent(tid)}/messages`,
		),
	create: (title?: string) =>
		http<Session>("/v1/sessions", {
			method: "POST",
			body: JSON.stringify({ title: title ?? "" }),
		}),
	rename: (tid: string, title: string) =>
		http<Ok>(`/v1/sessions/${encodeURIComponent(tid)}`, {
			method: "PATCH",
			body: JSON.stringify({ title }),
		}),
	setAutoApprove: (tid: string, auto_approve: boolean) =>
		http<Ok>(`/v1/sessions/${encodeURIComponent(tid)}`, {
			method: "PATCH",
			body: JSON.stringify({ auto_approve }),
		}),
	setPinned: (tid: string, pinned: boolean) =>
		http<Ok>(`/v1/sessions/${encodeURIComponent(tid)}`, {
			method: "PATCH",
			body: JSON.stringify({ pinned }),
		}),
	remove: (tid: string) =>
		http<Ok>(`/v1/sessions/${encodeURIComponent(tid)}`, { method: "DELETE" }),
	importConversation: (messages: unknown[], title?: string) =>
		http<{ ok: boolean; thread_id?: string; count?: number; error?: string }>(
			"/v1/sessions/import",
			{ method: "POST", body: JSON.stringify({ messages, title }) },
		),
};

export function useSessions() {
	return useQuery({ queryKey: ["sessions"], queryFn: sessionApi.list });
}

export function useSessionMutations() {
	const qc = useQueryClient();
	const onSuccess = () => qc.invalidateQueries({ queryKey: ["sessions"] });
	return {
		rename: useMutation({
			mutationFn: ({ tid, title }: { tid: string; title: string }) =>
				sessionApi.rename(tid, title),
			onSuccess,
		}),
		remove: useMutation({
			mutationFn: (tid: string) => sessionApi.remove(tid),
			onSuccess,
		}),
		setPinned: useMutation({
			mutationFn: ({ tid, pinned }: { tid: string; pinned: boolean }) =>
				sessionApi.setPinned(tid, pinned),
			onSuccess,
		}),
	};
}
