import { useModels, useModelsConfig } from "@/api/queries";
import type { ModelInfo, ReasoningEffort } from "@/api/types";
import {
	Select,
	SelectContent,
	SelectGroup,
	SelectItem,
	SelectLabel,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { useChatStore } from "@/store/chat";

const EFFORTS: { value: ReasoningEffort; label: string }[] = [
	{ value: "off", label: "No reasoning" },
	{ value: "minimal", label: "Minimal" },
	{ value: "low", label: "Low" },
	{ value: "medium", label: "Medium" },
	{ value: "high", label: "High" },
	{ value: "extra_high", label: "Extra High" },
];

// Model + reasoning-effort selectors, wired to the Zustand store the chat
// runtime reads at send time. Models are grouped by provider (webui-style
// optgroups); effort is disabled for non-reasoning models.
export function ModelPicker() {
	const { data } = useModels();
	const { data: cfg } = useModelsConfig();
	const models = data?.data ?? [];
	const providers = cfg?.providers ?? [];
	const model = useChatStore((s) => s.model);
	const setModel = useChatStore((s) => s.setModel);
	const effort = useChatStore((s) => s.reasoningEffort);
	const setEffort = useChatStore((s) => s.setReasoningEffort);

	const supportsReasoning =
		models.find((m) => m.id === model)?.supports_reasoning ?? true;

	// Group by provider, ordered by the provider catalog (then any extras last).
	const labelFor = (id: string) =>
		providers.find((p) => p.id === id)?.label ?? id;
	const order: string[] = providers.map((p) => p.id);
	const grouped = new Map<string, ModelInfo[]>();
	for (const m of models) {
		const key = m.provider ?? "other";
		const arr = grouped.get(key);
		if (arr) arr.push(m);
		else grouped.set(key, [m]);
	}
	const groupKeys = [...grouped.keys()].sort(
		(a, b) => (order.indexOf(a) + 1 || 999) - (order.indexOf(b) + 1 || 999),
	);

	return (
		<div className="flex items-center gap-2">
			<Select value={model} onValueChange={(v) => v && setModel(v)}>
				<SelectTrigger size="sm" className="w-[180px] text-xs">
					<SelectValue placeholder="Select model" />
				</SelectTrigger>
				<SelectContent className="max-w-[320px]">
					{groupKeys.map((key) => (
						<SelectGroup key={key}>
							<SelectLabel className="text-[11px] uppercase tracking-wide text-muted-foreground">
								{labelFor(key)}
							</SelectLabel>
							{(grouped.get(key) ?? []).map((m) => (
								<SelectItem key={m.id} value={m.id} className="text-xs">
									{m.id}
									{m.supports_reasoning ? " · 🧠" : ""}
								</SelectItem>
							))}
						</SelectGroup>
					))}
				</SelectContent>
			</Select>
			<Select
				value={effort}
				onValueChange={(v) => v && setEffort(v as ReasoningEffort)}
				disabled={!supportsReasoning}
			>
				<SelectTrigger size="sm" className="w-[150px] text-xs">
					<SelectValue placeholder="Reasoning" />
				</SelectTrigger>
				<SelectContent>
					{EFFORTS.map((e) => (
						<SelectItem key={e.value} value={e.value} className="text-xs">
							{e.label}
						</SelectItem>
					))}
				</SelectContent>
			</Select>
		</div>
	);
}
