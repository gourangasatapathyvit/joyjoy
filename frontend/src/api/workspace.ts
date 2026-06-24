import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCapabilities } from "@/api/capabilities";
import { http } from "@/api/client";
import type {
	OkPath as Ok,
	WorkspaceFileContent,
	WorkspaceNode,
} from "@/api/types";
import {
	flattenWorkspaceFilePaths,
	parseWorkspaceMediaUrl,
	relWorkspacePath,
} from "@/lib/media";

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
	upload: (threadId: string, dir: string, file: File): Promise<Ok> => {
		const fd = new FormData();
		fd.append("thread_id", threadId);
		fd.append("dir", dir);
		fd.append("file", file);
		return http<Ok>("/v1/workspace/upload", { method: "POST", body: fd });
	},
};

export function useWorkspaceTree(threadId: string) {
	return useQuery({
		queryKey: ["workspace", "tree", threadId],
		queryFn: () => workspaceApi.tree(threadId),
		enabled: !!threadId,
	});
}

// Readiness of a workspace-served media URL, used to GATE inline rendering so we
// never fetch a file the sandbox hasn't written yet (the transient read-after-write
// 404). Driven by the workspace tree — which is refetched after each run's
// tool.completed — so a preview flips from "pending" to "ready" reactively once
// the file appears. "na" = not gated (data:/external URL, host mode, or an
// absolute path outside the mount → fall back to optimistic fetch).
export type MediaReadiness = "na" | "pending" | "ready" | "absent";

export function useMediaReady(url: string): MediaReadiness {
	const parsed = parseWorkspaceMediaUrl(url);
	const caps = useCapabilities();
	const tree = useWorkspaceTree(parsed?.threadId ?? "");
	if (!parsed) return "na";
	// Only the sandbox has the write-visibility lag; in host mode files may also
	// live outside the workspace tree, so don't gate there.
	if (caps.data?.sandbox && !caps.data.sandbox.enabled) return "na";
	const mount = caps.data?.sandbox?.mount_path ?? "/workspace";
	const rel = relWorkspacePath(parsed.path, mount);
	if (rel == null) return "na"; // absolute path outside the mount — can't gate
	if (flattenWorkspaceFilePaths(tree.data?.tree ?? []).has(rel)) return "ready";
	if (tree.isLoading || tree.isFetching || !tree.data) return "pending";
	return "absent";
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
