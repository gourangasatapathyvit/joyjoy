import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { dataApi } from "@/api/data";
import type { MemorySection } from "@/api/types";

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
export function useSkillContent(name: string | null) {
	return useQuery({
		queryKey: ["skill-content", name],
		queryFn: () => dataApi.skillContent(name as string),
		enabled: !!name,
	});
}
export function useMemory() {
	return useQuery({ queryKey: ["memory"], queryFn: dataApi.memory });
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
	const onSuccess = () => qc.invalidateQueries({ queryKey: ["skills"] });
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
		mutationFn: ({
			section,
			content,
		}: {
			section: MemorySection;
			content: string;
		}) => dataApi.writeMemory(section, content),
		onSuccess: () => qc.invalidateQueries({ queryKey: ["memory"] }),
	});
}
