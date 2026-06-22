import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dataApi } from "@/api/data";

// ── Reads ──────────────────────────────────────────────────────────────────
export function useModels() {
	return useQuery({ queryKey: ["models"], queryFn: dataApi.models });
}
export function useModelsConfig() {
	return useQuery({
		queryKey: ["models", "config"],
		queryFn: dataApi.modelsConfig,
	});
}
export function useMcpServers() {
	return useQuery({
		queryKey: ["mcp", "servers"],
		queryFn: dataApi.mcpServers,
	});
}
export function useMcpTools() {
	return useQuery({ queryKey: ["mcp", "tools"], queryFn: dataApi.mcpTools });
}
export function useSkills() {
	return useQuery({ queryKey: ["skills"], queryFn: dataApi.skills });
}
export function useSkillContent(name: string | null, file?: string | null) {
	return useQuery({
		queryKey: ["skill-content", name, file ?? null],
		queryFn: () => dataApi.skillContent(name as string, file ?? undefined),
		enabled: !!name,
	});
}
export function useMemory() {
	return useQuery({ queryKey: ["memory"], queryFn: dataApi.memory });
}
export function useMemoryFiles() {
	return useQuery({ queryKey: ["memories"], queryFn: dataApi.memoryFiles });
}
export function useMemoryFile(path: string | null) {
	return useQuery({
		queryKey: ["memory-file", path],
		queryFn: () => dataApi.readMemoryFile(path as string),
		enabled: !!path,
	});
}

// ── Mutations (invalidate the relevant cache on success) ─────────────────────
export function useMcpMutations() {
	const qc = useQueryClient();
	const onSuccess = () => qc.invalidateQueries({ queryKey: ["mcp"] });
	return {
		save: useMutation({
			mutationFn: ({
				name,
				cfg,
			}: {
				name: string;
				cfg: Record<string, unknown>;
			}) => dataApi.saveMcp(name, cfg),
			onSuccess,
		}),
		toggle: useMutation({
			mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
				dataApi.toggleMcp(name, enabled),
			onSuccess,
		}),
		remove: useMutation({
			mutationFn: (name: string) => dataApi.deleteMcp(name),
			onSuccess,
		}),
	};
}
export function useSkillMutations() {
	const qc = useQueryClient();
	const onSuccess = () => {
		qc.invalidateQueries({ queryKey: ["skills"] });
		qc.invalidateQueries({ queryKey: ["skill-content"] });
	};
	return {
		save: useMutation({
			mutationFn: ({ name, content }: { name: string; content: string }) =>
				dataApi.saveSkill(name, content),
			onSuccess,
		}),
		toggle: useMutation({
			mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
				dataApi.toggleSkill(name, enabled),
			onSuccess,
		}),
		remove: useMutation({
			mutationFn: (name: string) => dataApi.deleteSkill(name),
			onSuccess,
		}),
		saveFile: useMutation({
			mutationFn: ({
				skill,
				path,
				content,
				encoding,
			}: {
				skill: string;
				path: string;
				content: string;
				encoding?: string;
			}) => dataApi.saveSkillFile(skill, path, content, encoding),
			onSuccess,
		}),
		deleteFile: useMutation({
			mutationFn: ({ skill, path }: { skill: string; path: string }) =>
				dataApi.deleteSkillFile(skill, path),
			onSuccess,
		}),
		importZip: useMutation({
			mutationFn: ({ name, zip_b64 }: { name: string; zip_b64: string }) =>
				dataApi.importSkill(name, zip_b64),
			onSuccess,
		}),
	};
}
export function useModelMutations() {
	const qc = useQueryClient();
	const onSuccess = () => qc.invalidateQueries({ queryKey: ["models"] });
	return {
		save: useMutation({
			mutationFn: (entry: Record<string, unknown>) => dataApi.saveModel(entry),
			onSuccess,
		}),
		remove: useMutation({
			mutationFn: (id: string) => dataApi.deleteModel(id),
			onSuccess,
		}),
		test: useMutation({ mutationFn: (id: string) => dataApi.testModel(id) }),
	};
}
export function useWriteMemory() {
	const qc = useQueryClient();
	return useMutation({
		mutationFn: (content: string) => dataApi.writeMemory(content),
		onSuccess: () => qc.invalidateQueries({ queryKey: ["memory"] }),
	});
}
export function useMemoryFileMutations() {
	const qc = useQueryClient();
	const onSuccess = () => {
		qc.invalidateQueries({ queryKey: ["memories"] });
		qc.invalidateQueries({ queryKey: ["memory-file"] });
	};
	return {
		save: useMutation({
			mutationFn: ({ path, content }: { path: string; content: string }) =>
				dataApi.writeMemoryFile(path, content),
			onSuccess,
		}),
		remove: useMutation({
			mutationFn: (path: string) => dataApi.deleteMemoryFile(path),
			onSuccess,
		}),
		toggle: useMutation({
			mutationFn: ({ path, enabled }: { path: string; enabled: boolean }) =>
				dataApi.toggleMemoryFile(path, enabled),
			onSuccess,
		}),
	};
}
