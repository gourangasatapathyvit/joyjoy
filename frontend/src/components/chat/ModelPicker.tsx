import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useModels, useModelsConfig } from "@/api/queries";
import type { ListModelsResponse, ReasoningEffort } from "@/api/types";
import {
	type ModelOption,
	ModelSelector,
} from "@/components/assistant-ui/model-selector";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/store/chat";

// A row from GET /v1/models — carries the provider used for grouping/filtering.
type ModelRow = ListModelsResponse["data"][number];

// Reasoning-effort values → i18n key suffix (under `model.*`).
const EFFORTS: { value: ReasoningEffort; key: string }[] = [
	{ value: "off", key: "off" },
	{ value: "minimal", key: "minimal" },
	{ value: "low", key: "low" },
	{ value: "medium", key: "medium" },
	{ value: "high", key: "high" },
	{ value: "extra_high", key: "extraHigh" },
];

// A small toggle chip for the provider filter row.
function FilterChip({
	active,
	onClick,
	children,
}: {
	active: boolean;
	onClick: () => void;
	children: React.ReactNode;
}) {
	return (
		<button
			type="button"
			onClick={onClick}
			data-state={active ? "on" : "off"}
			className={cn(
				"focus-visible:ring-ring/50 rounded-full border px-2 py-0.5 text-xs transition-colors outline-none focus-visible:ring-2",
				active
					? "bg-accent text-accent-foreground border-transparent font-medium"
					: "text-muted-foreground hover:bg-accent/50 border-transparent",
			)}
		>
			{children}
		</button>
	);
}

// Model + reasoning-effort selectors, wired to the Zustand store the chat
// runtime reads at send time. The model selector is assistant-ui's Model
// Selector (searchable cmdk popover) with provider filter chips + per-provider
// groups; effort stays a separate select (disabled for non-reasoning models).
export function ModelPicker() {
	const { t } = useTranslation();
	const { data } = useModels();
	const { data: cfg } = useModelsConfig();
	const models = data?.data ?? [];
	const providers = cfg?.providers ?? [];
	const model = useChatStore((s) => s.model);
	const setModel = useChatStore((s) => s.setModel);
	const effort = useChatStore((s) => s.reasoningEffort);
	const setEffort = useChatStore((s) => s.setReasoningEffort);
	const autoApprove = useChatStore((s) => s.autoApprove);
	const setAutoApprove = useChatStore((s) => s.setAutoApprove);

	// null = show every provider; otherwise restrict the list to one provider.
	const [providerFilter, setProviderFilter] = useState<string | null>(null);

	const supportsReasoning =
		models.find((m) => m.id === model)?.supports_reasoning ?? true;

	const labelFor = (id: string) =>
		providers.find((p) => p.id === id)?.label ?? id;

	const toOption = (m: ModelRow): ModelOption => ({
		id: m.id,
		name: m.id,
		// Searchable by provider label + a "reasoning" hint, beyond id/name.
		keywords: [
			labelFor(m.provider ?? "other"),
			m.provider ?? "other",
			m.supports_reasoning ? "reasoning" : "",
		].filter(Boolean),
	});

	// All options drive Root (selected-model resolution + cmdk value seeding).
	const options: ModelOption[] = models.map(toOption);

	// Group by provider, ordered by the provider catalog (extras last).
	const order: string[] = providers.map((p) => p.id);
	const grouped = new Map<string, ModelRow[]>();
	for (const m of models) {
		const key = m.provider ?? "other";
		const arr = grouped.get(key);
		if (arr) arr.push(m);
		else grouped.set(key, [m]);
	}
	const groupKeys = [...grouped.keys()].sort(
		(a, b) => (order.indexOf(a) + 1 || 999) - (order.indexOf(b) + 1 || 999),
	);
	const visibleKeys = providerFilter
		? groupKeys.filter((k) => k === providerFilter)
		: groupKeys;

	return (
		<div className="flex items-center gap-2">
			<ModelSelector.Root
				models={options}
				value={model}
				onValueChange={(v) => v && setModel(v)}
			>
				<ModelSelector.Trigger size="sm" className="w-[180px]">
					<ModelSelector.Value placeholder={t("model.selectModel")} />
				</ModelSelector.Trigger>
				<ModelSelector.Content className="w-[300px]">
					{groupKeys.length > 1 && (
						<div className="flex flex-wrap items-center gap-1 border-b px-2 py-2">
							<FilterChip
								active={providerFilter === null}
								onClick={() => setProviderFilter(null)}
							>
								{t("model.allProviders")}
							</FilterChip>
							{groupKeys.map((k) => (
								<FilterChip
									key={k}
									active={providerFilter === k}
									onClick={() => setProviderFilter(k)}
								>
									{labelFor(k)}
								</FilterChip>
							))}
						</div>
					)}
					<ModelSelector.Search placeholder={t("model.searchPlaceholder")} />
					<ModelSelector.List>
						<ModelSelector.Empty>{t("model.noModels")}</ModelSelector.Empty>
						{visibleKeys.map((key) => (
							<ModelSelector.Group key={key} heading={labelFor(key)}>
								{(grouped.get(key) ?? []).map((m) => (
									<ModelSelector.Item key={m.id} model={toOption(m)} />
								))}
							</ModelSelector.Group>
						))}
					</ModelSelector.List>
				</ModelSelector.Content>
			</ModelSelector.Root>
			<Select
				value={effort}
				onValueChange={(v) => v && setEffort(v as ReasoningEffort)}
				disabled={!supportsReasoning}
			>
				<SelectTrigger size="sm" className="w-[150px] text-xs">
					<SelectValue placeholder={t("model.reasoning")} />
				</SelectTrigger>
				<SelectContent>
					{EFFORTS.map((e) => (
						<SelectItem key={e.value} value={e.value} className="text-xs">
							{t(`model.${e.key}`)}
						</SelectItem>
					))}
				</SelectContent>
			</Select>
			<label
				htmlFor="auto-approve-switch"
				className="flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground"
				title={t("composer.autoApproveHint")}
			>
				<Switch
					id="auto-approve-switch"
					size="sm"
					checked={autoApprove}
					onCheckedChange={setAutoApprove}
				/>
				{t("composer.autoApprove")}
			</label>
		</div>
	);
}
