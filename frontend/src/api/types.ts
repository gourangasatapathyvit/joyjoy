// ─────────────────────────────────────────────────────────────────────────
// joyjoy API contract — the single source of truth for the backend wire shape.
// Phase 1+ talks to the backend /v1 directly; these mirror app/runs.py _emit().
// ─────────────────────────────────────────────────────────────────────────

export type Role = "user" | "assistant" | "system" | "tool";

// A media artifact surfaced by the agent (base64 read_file blocks → data URL).
// Path-based media (MEDIA: markers, written workspace files) is resolved to URLs
// on the client instead — see lib/media.ts.
export interface MediaItem {
	kind: "image" | "audio" | "video" | "file";
	mime_type: string;
	filename?: string | null;
	data_url: string;
}

export interface ChatMessage {
	id: string;
	role: Role;
	content: string;
	createdAt?: number;
}

// SSE events from GET /v1/runs/{id}/events (each arrives as a `data:` JSON line,
// terminated by a literal `data: [DONE]`). Field names match app/runs.py exactly.
export type RunEvent =
	| { event: "message.delta"; delta: string }
	| { event: "reasoning.available"; text: string; delta?: string }
	| {
			event: "tool.started";
			tool?: string;
			name?: string;
			toolCallId?: string;
			args?: unknown;
			label?: string;
	  }
	| {
			event: "tool.completed";
			tool?: string;
			name?: string;
			toolCallId?: string;
			status?: string;
			is_error?: boolean;
			result?: string;
			media?: MediaItem[];
	  }
	| {
			event: "approval.request";
			approval_id: string;
			run_id: string;
			tool?: string;
			name?: string;
			args?: unknown;
			command?: string;
			description?: string;
			risk_level?: string;
			choices?: string[];
			allow_permanent?: boolean;
	  }
	| { event: "run.completed"; output?: string }
	| { event: "run.failed"; error?: string }
	| { event: "run.cancelled" };

// POST /v1/runs body. `input` is the user's prompt; thread_id keeps a conversation.
export interface CreateRunRequest {
	input: string;
	model?: string;
	reasoning_effort?: string;
	thread_id?: string;
}

export interface CreateRunResponse {
	run_id: string;
	id?: string;
	status?: string;
	model?: string;
}

export interface ModelInfo {
	id: string;
	label?: string;
	supports_reasoning?: boolean;
}

// ── Side-panel data shapes (mirror app/main.py /v1 handlers) ───────────────
export type ModelProvider =
	| "azure_openai"
	| "anthropic"
	| "bedrock"
	| "openai"
	| "gemini";

export interface ListModelsResponse {
	object: "list";
	data: Array<{
		id: string;
		provider?: ModelProvider;
		supports_reasoning?: boolean;
	}>;
}

// Reasoning effort levels the backend accepts ("off" → omit / no reasoning).
export type ReasoningEffort =
	| "off"
	| "minimal"
	| "low"
	| "medium"
	| "high"
	| "extra_high";

export interface McpServer {
	name: string;
	scope: "global" | "user";
	transport: string;
	enabled: boolean;
	status: "configured" | "active" | "invalid_config" | "disabled" | string;
	tool_count: number | null;
	command?: string;
	args?: string[];
	url?: string;
}

export interface McpToolParam {
	name: string;
	type: string;
	required: boolean;
	description: string;
}

export interface McpTool {
	name: string;
	server: string;
	scope: "global" | "user";
	status: string;
	description: string;
	schema_summary: McpToolParam[];
}

export interface Skill {
	name: string;
	description: string;
	scope: "global" | "user";
	editable: boolean;
	enabled: boolean;
	builtin?: boolean;
}

export interface SkillContent {
	success: boolean;
	name: string;
	scope: "global" | "user";
	editable: boolean;
	enabled?: boolean;
	content: string;
	error?: string;
}

export interface Memory {
	memory: string;
	user: string;
	soul: string;
}
export type MemorySection = "memory" | "user" | "soul";

// ── Sessions (conversation threads) ────────────────────────────────────────
export interface Session {
	thread_id: string;
	title: string;
	created_at: number;
	updated_at: number;
	model?: string;
}

// A persisted message as returned by GET /v1/sessions/{tid}/messages.
export interface SessionMessageWire {
	role: "user" | "assistant" | "tool" | "system";
	content: string;
	tool_calls?: { id: string; name: string; args: Record<string, unknown> }[];
	tool_call_id?: string;
	name?: string;
	media?: MediaItem[];
}

// ── Models / Providers config (Providers panel CRUD) ───────────────────────
// The backend returns a provider field-schema (PROVIDER_TYPES) that drives the
// add/edit form, plus the user's + global models (secrets masked).
export interface ProviderField {
	key: string;
	label: string;
	required: boolean;
	placeholder?: string;
	secret?: boolean;
}
export interface ProviderType {
	id: ModelProvider;
	label: string;
	fields: ProviderField[];
}
export interface ModelConfigItem {
	id: string;
	provider: ModelProvider;
	deployment?: string;
	endpoint?: string;
	api_version?: string;
	region?: string;
	max_tokens?: number;
	aws_access_key_id?: string;
	has_key?: boolean;
	api_key_masked?: string;
	has_aws_secret?: boolean;
	supports_reasoning?: boolean;
	scope: "global" | "user";
	editable: boolean;
}
export interface ModelsConfigResponse {
	models: ModelConfigItem[];
	providers: ProviderType[];
}
export interface ModelTestResult {
	id: string;
	standard: { ok: boolean; error?: string };
	reasoning: {
		supported: boolean;
		ok: boolean;
		visible_text: boolean;
		error?: string;
	};
}

// ── Workspace (the agent's per-user working-dir file browser) ──────────────
export interface WorkspaceNode {
	name: string;
	path: string;
	type: "dir" | "file";
	size?: number;
	children?: WorkspaceNode[];
}
export interface WorkspaceFileContent {
	path: string;
	content: string;
	size: number;
	truncated: boolean;
	binary: boolean;
}
