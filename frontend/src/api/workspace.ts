import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { http } from "@/api/client";
import type { WorkspaceFileContent, WorkspaceNode } from "@/api/types";

type Ok = { ok: boolean; error?: string; path?: string };

// Every call is scoped to a chat's workspace via thread_id; the backend maps it
// to the session's workspace_id (forks share one). The dock passes the active
// thread so it shows exactly that conversation's files.
export const workspaceApi = {
	tree: (threadId: string) =>
		http<{ tree: WorkspaceNode[] }>(
			`/v1/workspace/tree?thread_id=${encodeURIComponent(threadId)}`,
		),
	file: (threadId: string, path: string) =>
		http<WorkspaceFileContent>(
			`/v1/workspace/file?thread_id=${encodeURIComponent(threadId)}&path=${encodeURIComponent(path)}`,
		),
	rawUrl: (threadId: string, path: string) =>
		`/v1/workspace/raw?thread_id=${encodeURIComponent(threadId)}&path=${encodeURIComponent(path)}`,
	save: (threadId: string, path: string, content: string) =>
		http<Ok>("/v1/workspace/save", {
			method: "POST",
			body: JSON.stringify({ thread_id: threadId, path, content }),
		}),
	mkdir: (threadId: string, path: string) =>
		http<Ok>("/v1/workspace/mkdir", {
			method: "POST",
			body: JSON.stringify({ thread_id: threadId, path }),
		}),
	remove: (threadId: string, path: string) =>
		http<Ok>("/v1/workspace/delete", {
			method: "POST",
			body: JSON.stringify({ thread_id: threadId, path }),
		}),
	rename: (threadId: string, from: string, to: string) =>
		http<Ok>("/v1/workspace/rename", {
			method: "POST",
			body: JSON.stringify({ thread_id: threadId, from, to }),
		}),
	upload: async (threadId: string, dir: string, file: File): Promise<Ok> => {
		const fd = new FormData();
		fd.append("thread_id", threadId);
		fd.append("dir", dir);
		fd.append("file", file);
		const r = await fetch("/v1/workspace/upload", {
			method: "POST",
			body: fd,
			credentials: "include",
		});
		return r.json();
	},
};

export function useWorkspaceTree(threadId: string) {
	return useQuery({
		queryKey: ["workspace", "tree", threadId],
		queryFn: () => workspaceApi.tree(threadId),
		enabled: !!threadId,
	});
}

export function useWorkspaceFile(
	threadId: string,
	path: string | null,
	enabled = true,
) {
	return useQuery({
		queryKey: ["workspace", "file", threadId, path],
		queryFn: () => workspaceApi.file(threadId, path as string),
		enabled: !!threadId && !!path && enabled,
	});
}

export function useWorkspaceMutations(threadId: string) {
	const qc = useQueryClient();
	const onSuccess = () => qc.invalidateQueries({ queryKey: ["workspace"] });
	return {
		save: useMutation({
			mutationFn: ({ path, content }: { path: string; content: string }) =>
				workspaceApi.save(threadId, path, content),
			onSuccess,
		}),
		mkdir: useMutation({
			mutationFn: (path: string) => workspaceApi.mkdir(threadId, path),
			onSuccess,
		}),
		remove: useMutation({
			mutationFn: (path: string) => workspaceApi.remove(threadId, path),
			onSuccess,
		}),
		rename: useMutation({
			mutationFn: ({ from, to }: { from: string; to: string }) =>
				workspaceApi.rename(threadId, from, to),
			onSuccess,
		}),
		upload: useMutation({
			mutationFn: ({ dir, file }: { dir: string; file: File }) =>
				workspaceApi.upload(threadId, dir, file),
			onSuccess,
		}),
	};
}
