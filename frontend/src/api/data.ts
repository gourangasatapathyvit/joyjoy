import { http } from "@/api/client";
import type {
	ListModelsResponse,
	McpServer,
	McpTool,
	Memory,
	MemorySection,
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
	skillContent: (name: string) =>
		http<SkillContent>(`/v1/skills/content?name=${encodeURIComponent(name)}`),
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

	memory: () =>
		http<Memory & { external_notes_enabled?: boolean }>("/v1/memory"),
	writeMemory: (section: MemorySection, content: string) =>
		http<Ok>("/v1/memory/write", {
			method: "POST",
			body: JSON.stringify({ section, content }),
		}),
};
