import { useTranslation } from "react-i18next";
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
import { Switch } from "@/components/ui/switch";
import { useChatStore } from "@/store/chat";

// Reasoning-effort values → i18n key suffix (under `model.*`).
const EFFORTS: { value: ReasoningEffort; key: string }[] = [
	{ value: "off", key: "off" },
	{ value: "minimal", key: "minimal" },
	{ value: "low", key: "low" },
	{ value: "medium", key: "medium" },
	{ value: "high", key: "high" },
	{ value: "extra_high", key: "extraHigh" },
];

// Model + reasoning-effort selectors, wired to the Zustand store the chat
// runtime reads at send time. Models are grouped by provider (webui-style
// optgroups); effort is disabled for non-reasoning models.
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
					<SelectValue placeholder={t("model.selectModel")} />
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
