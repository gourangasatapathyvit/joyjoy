import { http } from "@/api/client";
import type {
	ListModelsResponse,
	McpServer,
	McpTool,
	Memory,
	MemoryFile,
	ModelsConfigResponse,
	ModelTestResult,
	Skill,
	SkillContent,
} from "@/api/types";

type Ok = { ok: boolean; error?: string };

// Typed wrappers over the backend /v1 data endpoints. All are per-user (the dev
// proxy injects X-User-Id); writes to global names are rejected server-side.
export const dataApi = {
	models: () => http<ListModelsResponse>("/v1/models"),

	mcpServers: () => http<{ servers: McpServer[] }>("/v1/mcp/servers"),
	mcpTools: () => http<{ tools: McpTool[]; total: number }>("/v1/mcp/tools"),
	saveMcp: (name: string, cfg: Record<string, unknown>) =>
		http<Ok>(`/v1/mcp/servers/${encodeURIComponent(name)}`, {
			method: "PUT",
			body: JSON.stringify(cfg),
		}),
	toggleMcp: (name: string, enabled: boolean) =>
		http<Ok>(`/v1/mcp/servers/${encodeURIComponent(name)}`, {
			method: "PATCH",
			body: JSON.stringify({ enabled }),
		}),
	deleteMcp: (name: string) =>
		http<Ok>(`/v1/mcp/servers/${encodeURIComponent(name)}`, {
			method: "DELETE",
		}),

	skills: () => http<{ skills: Skill[] }>("/v1/skills"),
	skillContent: (name: string, file?: string) =>
		http<SkillContent>(
			`/v1/skills/content?name=${encodeURIComponent(name)}` +
				(file ? `&file=${encodeURIComponent(file)}` : ""),
		),
	saveSkill: (name: string, content: string) =>
		http<Ok & { name?: string }>("/v1/skills/save", {
			method: "POST",
			body: JSON.stringify({ name, content }),
		}),
	toggleSkill: (name: string, enabled: boolean) =>
		http<Ok>("/v1/skills/toggle", {
			method: "POST",
			body: JSON.stringify({ name, enabled }),
		}),
	deleteSkill: (name: string) =>
		http<Ok>("/v1/skills/delete", {
			method: "POST",
			body: JSON.stringify({ name }),
		}),
	// Multi-file user skills: per-file save/delete + whole-skill zip import.
	saveSkillFile: (
		skill: string,
		path: string,
		content: string,
		encoding = "utf-8",
	) =>
		http<Ok & { path?: string }>("/v1/skills/files/save", {
			method: "POST",
			body: JSON.stringify({ skill, path, content, encoding }),
		}),
	deleteSkillFile: (skill: string, path: string) =>
		http<Ok>("/v1/skills/files/delete", {
			method: "POST",
			body: JSON.stringify({ skill, path }),
		}),
	importSkill: (name: string, zip_b64: string) =>
		http<Ok & { files?: number }>("/v1/skills/import", {
			method: "POST",
			body: JSON.stringify({ name, zip_b64 }),
		}),

	modelsConfig: () => http<ModelsConfigResponse>("/v1/models/config"),
	saveModel: (entry: Record<string, unknown>) =>
		http<Ok>("/v1/models/config/save", {
			method: "POST",
			body: JSON.stringify(entry),
		}),
	deleteModel: (id: string) =>
		http<Ok>("/v1/models/config/delete", {
			method: "POST",
			body: JSON.stringify({ id }),
		}),
	testModel: (id: string) =>
		http<ModelTestResult>("/v1/models/config/test", {
			method: "POST",
			body: JSON.stringify({ id }),
		}),

	memory: () => http<Memory>("/v1/memory"),
	writeMemory: (content: string) =>
		http<Ok>("/v1/memory/write", {
			method: "POST",
			body: JSON.stringify({ content }),
		}),

	// Dynamic /memories/ files (agent's on-demand, cross-session memory folder).
	memoryFiles: () => http<{ files: MemoryFile[] }>("/v1/memories"),
	readMemoryFile: (path: string) =>
		http<{ path: string; content: string; enabled: boolean; error?: string }>(
			`/v1/memories/file?path=${encodeURIComponent(path)}`,
		),
	writeMemoryFile: (path: string, content: string) =>
		http<Ok>("/v1/memories/file", {
			method: "POST",
			body: JSON.stringify({ path, content }),
		}),
	deleteMemoryFile: (path: string) =>
		http<Ok>("/v1/memories/delete", {
			method: "POST",
			body: JSON.stringify({ path }),
		}),
	toggleMemoryFile: (path: string, enabled: boolean) =>
		http<Ok>("/v1/memories/toggle", {
			method: "POST",
			body: JSON.stringify({ path, enabled }),
		}),
};
