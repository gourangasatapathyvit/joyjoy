import { Plus } from "lucide-react";
import { useState } from "react";
import { useModelMutations, useModelsConfig } from "@/api/queries";
import type {
	ModelConfigItem,
	ModelTestResult,
	ProviderType,
} from "@/api/types";
import { PanelLayout } from "@/components/layout/PanelLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
	Dialog,
	DialogContent,
	DialogHeader,
	DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
	Select,
	SelectContent,
	SelectItem,
	SelectTrigger,
	SelectValue,
} from "@/components/ui/select";

// Add/edit a per-user model. Fields are driven by the provider's field-schema
// (PROVIDER_TYPES from the backend). Secrets left blank keep the stored value.
function ProviderModelDialog({
	providers,
	initial,
	onClose,
}: {
	providers: ProviderType[];
	initial: ModelConfigItem | null;
	onClose: () => void;
}) {
	const { save } = useModelMutations();
	const editing = !!initial;
	const [provider, setProvider] = useState<string>(
		initial?.provider ?? providers[0]?.id ?? "azure_openai",
	);
	const schema = providers.find((p) => p.id === provider) ?? providers[0];
	const [values, setValues] = useState<Record<string, string>>(() => {
		const v: Record<string, string> = {};
		if (initial) {
			for (const k of [
				"id",
				"deployment",
				"endpoint",
				"api_version",
				"region",
				"aws_access_key_id",
			] as const) {
				const raw = initial[k];
				if (raw != null) v[k] = String(raw);
			}
			if (initial.max_tokens) v.max_tokens = String(initial.max_tokens);
		}
		return v;
	});
	const [err, setErr] = useState<string | null>(null);
	const setField = (k: string, val: string) =>
		setValues((p) => ({ ...p, [k]: val }));

	const onSave = () => {
		const entry: Record<string, unknown> = { provider };
		for (const f of schema?.fields ?? []) {
			const val = (values[f.key] ?? "").trim();
			if (val) entry[f.key] = val;
		}
		if (!entry.id) {
			setErr("Model ID is required");
			return;
		}
		setErr(null);
		save.mutate(entry, {
			onSuccess: (res) =>
				res?.ok === false ? setErr(res.error ?? "Save failed") : onClose(),
			onError: () => setErr("Save failed"),
		});
	};

	return (
		<Dialog open onOpenChange={(o) => !o && onClose()}>
			<DialogContent className="max-w-lg">
				<DialogHeader>
					<DialogTitle>
						{editing ? `Edit ${initial?.id}` : "Add model"}
					</DialogTitle>
				</DialogHeader>
				<div className="space-y-3">
					<div className="space-y-1.5">
						<Label htmlFor="prov">Provider</Label>
						<Select value={provider} onValueChange={(v) => v && setProvider(v)}>
							<SelectTrigger id="prov">
								<SelectValue />
							</SelectTrigger>
							<SelectContent>
								{providers.map((p) => (
									<SelectItem key={p.id} value={p.id}>
										{p.label}
									</SelectItem>
								))}
							</SelectContent>
						</Select>
					</div>
					{schema?.fields.map((f) => (
						<div key={f.key} className="space-y-1.5">
							<Label htmlFor={`f-${f.key}`}>
								{f.label}
								{f.required && <span className="text-destructive"> *</span>}
							</Label>
							<Input
								id={`f-${f.key}`}
								type={f.secret ? "password" : "text"}
								value={values[f.key] ?? ""}
								disabled={editing && f.key === "id"}
								onChange={(e) => setField(f.key, e.target.value)}
								placeholder={
									f.secret && editing && initial?.has_key
										? "•••• (unchanged)"
										: f.placeholder
								}
							/>
						</div>
					))}
					{err && <p className="text-xs text-destructive">{err}</p>}
					<div className="flex justify-end gap-2">
						<Button variant="ghost" onClick={onClose}>
							Cancel
						</Button>
						<Button onClick={onSave} disabled={save.isPending}>
							{save.isPending ? "Saving…" : "Save"}
						</Button>
					</div>
				</div>
			</DialogContent>
		</Dialog>
	);
}

export function ProvidersPanel() {
	const { data, isLoading } = useModelsConfig();
	const { remove, test } = useModelMutations();
	const models = data?.models ?? [];
	const providers = data?.providers ?? [];

	const [dialogOpen, setDialogOpen] = useState(false);
	const [editTarget, setEditTarget] = useState<ModelConfigItem | null>(null);
	const [testResults, setTestResults] = useState<
		Record<string, ModelTestResult>
	>({});
	const [testing, setTesting] = useState<string | null>(null);

	const openNew = () => {
		setEditTarget(null);
		setDialogOpen(true);
	};
	const openEdit = (m: ModelConfigItem) => {
		setEditTarget(m);
		setDialogOpen(true);
	};
	const runTest = (id: string) => {
		setTesting(id);
		test.mutate(id, {
			onSuccess: (res) => setTestResults((p) => ({ ...p, [id]: res })),
			onSettled: () => setTesting(null),
		});
	};

	return (
		<PanelLayout
			title="Providers"
			description="Model providers and credentials (global models are read-only)."
		>
			<div className="flex justify-end">
				<Button size="sm" variant="outline" onClick={openNew}>
					<Plus className="size-3.5" /> Add model
				</Button>
			</div>
			{isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
			{models.map((m) => {
				const tr = testResults[m.id];
				return (
					<Card
						key={`${m.scope}-${m.id}`}
						className="flex-row items-center justify-between gap-3 p-3"
					>
						<div className="min-w-0">
							<div className="flex flex-wrap items-center gap-2">
								<span className="font-mono text-sm font-medium">{m.id}</span>
								<Badge variant="outline" className="text-[10px]">
									{m.provider}
								</Badge>
								<Badge variant="outline" className="text-[10px]">
									{m.scope}
								</Badge>
								{m.supports_reasoning && (
									<Badge variant="secondary" className="text-[10px]">
										reasoning
									</Badge>
								)}
								{tr && (
									<Badge
										variant={tr.standard.ok ? "default" : "destructive"}
										className="text-[10px]"
									>
										{tr.standard.ok ? "test ok" : "test fail"}
									</Badge>
								)}
							</div>
							{m.endpoint && (
								<p className="truncate text-xs text-muted-foreground">
									{m.endpoint}
								</p>
							)}
							{tr && !tr.standard.ok && tr.standard.error && (
								<p className="truncate text-[11px] text-destructive">
									{tr.standard.error}
								</p>
							)}
						</div>
						<div className="flex shrink-0 items-center gap-2">
							<Button
								size="sm"
								variant="ghost"
								disabled={testing === m.id}
								onClick={() => runTest(m.id)}
							>
								{testing === m.id ? "Testing…" : "Test"}
							</Button>
							{m.editable ? (
								<>
									<Button size="sm" variant="ghost" onClick={() => openEdit(m)}>
										Edit
									</Button>
									<Button
										size="sm"
										variant="ghost"
										onClick={() => remove.mutate(m.id)}
									>
										Delete
									</Button>
								</>
							) : (
								<Badge variant="secondary" className="text-[10px]">
									read-only
								</Badge>
							)}
						</div>
					</Card>
				);
			})}
			{dialogOpen && providers.length > 0 && (
				<ProviderModelDialog
					key={editTarget?.id ?? "__new__"}
					providers={providers}
					initial={editTarget}
					onClose={() => setDialogOpen(false)}
				/>
			)}
		</PanelLayout>
	);
}
