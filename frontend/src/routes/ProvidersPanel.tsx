import { Check, ChevronDown, Plus, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
	useDiscoverModels,
	useModelMutations,
	useModelsConfig,
	useXaiOauthPoll,
	useXaiOauthStart,
} from "@/api/queries";
import type {
	DiscoveredModel,
	ModelConfigItem,
	ModelTestResult,
	ProviderType,
	XaiOauthStartResponse,
} from "@/api/types";
import { PanelLayout } from "@/components/layout/PanelLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
	Collapsible,
	CollapsibleContent,
	CollapsibleTrigger,
} from "@/components/ui/collapsible";
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
import { Switch } from "@/components/ui/switch";
import { NEW_ITEM } from "@/lib/constants";
import { cn } from "@/lib/utils";

// One selectable row in the discovered-models checklist. The capability tags are
// shown inline (muted) AND on hover via the native title, per the request.
function DiscoveredRow({
	model,
	checked,
	onToggle,
	capabilitiesLabel,
}: {
	model: DiscoveredModel;
	checked: boolean;
	onToggle: () => void;
	capabilitiesLabel: string;
}) {
	const caps = model.capabilities ?? [];
	const title = caps.length
		? `${capabilitiesLabel}: ${caps.join(", ")}`
		: undefined;
	return (
		<button
			type="button"
			onClick={onToggle}
			title={title}
			className={cn(
				"flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent",
				checked && "bg-accent",
			)}
		>
			<span
				className={cn(
					"flex size-4 shrink-0 items-center justify-center rounded border",
					checked
						? "border-primary bg-primary text-primary-foreground"
						: "border-input",
				)}
			>
				{checked && <Check className="size-3" />}
			</span>
			<span className="min-w-0 flex-1">
				<span className="block truncate font-mono text-xs">{model.id}</span>
				{model.label && model.label !== model.id && (
					<span className="block truncate text-[11px] text-muted-foreground">
						{model.label}
					</span>
				)}
			</span>
			{caps.slice(0, 2).map((c) => (
				<Badge
					key={c}
					variant="outline"
					className="hidden shrink-0 text-[9px] sm:inline-flex"
				>
					{c}
				</Badge>
			))}
			{caps.length > 2 && (
				<Badge
					variant="outline"
					className="hidden shrink-0 text-[9px] sm:inline-flex"
				>
					+{caps.length - 2}
				</Badge>
			)}
		</button>
	);
}

// xAI Grok device-code OAuth login (RFC 8628) — replaces the credential field
// form for the "xai_oauth" provider. Start → show the user_code + verification
// link → poll on the returned interval until the login completes, then hand the
// tokens up so the caller can run the normal discover/select/save-bulk flow.
function XaiOauthLogin({
	onAuthenticated,
}: {
	onAuthenticated: (tokens: {
		access_token: string;
		refresh_token?: string;
		expires_at?: number;
	}) => void;
}) {
	const { t } = useTranslation();
	const start = useXaiOauthStart();
	const poll = useXaiOauthPoll();
	const [data, setData] = useState<XaiOauthStartResponse | null>(null);
	const [phase, setPhase] = useState<"idle" | "waiting" | "done" | "error">(
		"idle",
	);
	const [err, setErr] = useState<string | null>(null);
	// The poll effect below intentionally keys off only [phase, data?.device_code] —
	// it must NOT restart (and re-register a fresh setInterval) every time the
	// parent re-renders and hands down a new `onAuthenticated` closure, or every
	// poll cycle would be cut short. Refs give the effect the latest callback/t
	// without needing either in its dependency list.
	const onAuthenticatedRef = useRef(onAuthenticated);
	onAuthenticatedRef.current = onAuthenticated;
	const tRef = useRef(t);
	tRef.current = t;

	const begin = () => {
		setErr(null);
		setData(null);
		setPhase("waiting");
		start.mutate(undefined, {
			onSuccess: (res) => {
				if (!res.ok || !res.device_code) {
					setErr(res.error ?? tRef.current("providers.xaiOauthFailed"));
					setPhase("error");
					return;
				}
				setData(res);
			},
			onError: () => {
				setErr(tRef.current("providers.xaiOauthFailed"));
				setPhase("error");
			},
		});
	};

	// biome-ignore lint/correctness/useExhaustiveDependencies: onAuthenticatedRef.current/tRef.current are refs (see their declaration above) read deliberately so this effect does NOT restart the setInterval on every parent re-render.
	useEffect(() => {
		if (phase !== "waiting" || !data?.device_code) return;
		const ms = Math.max(1, data.interval ?? 5) * 1000;
		let cancelled = false;
		const id = setInterval(() => {
			poll.mutate(data.device_code as string, {
				onSuccess: (res) => {
					if (cancelled) return;
					if (res.status === "complete" && res.access_token) {
						clearInterval(id);
						setPhase("done");
						onAuthenticatedRef.current({
							access_token: res.access_token,
							refresh_token: res.refresh_token,
							expires_at: res.expires_in
								? Date.now() / 1000 + res.expires_in
								: undefined,
						});
					} else if (res.status === "expired" || res.status === "error") {
						clearInterval(id);
						setErr(res.error ?? tRef.current("providers.xaiOauthFailed"));
						setPhase("error");
					}
				},
			});
		}, ms);
		return () => {
			cancelled = true;
			clearInterval(id);
		};
	}, [phase, data?.device_code, poll]);

	if (phase === "done") {
		return (
			<p className="text-xs text-muted-foreground">
				{t("providers.xaiOauthSuccess")}
			</p>
		);
	}

	return (
		<div className="space-y-3 rounded-md border p-3">
			{phase === "waiting" && data ? (
				<div className="space-y-2 text-center">
					<p className="text-xs text-muted-foreground">
						{t("providers.xaiOauthInstructions")}
					</p>
					<p className="font-mono text-lg font-semibold tracking-widest">
						{data.user_code}
					</p>
					<a
						href={data.verification_uri_complete || data.verification_uri}
						target="_blank"
						rel="noreferrer"
						className="block truncate text-xs text-primary underline"
					>
						{data.verification_uri_complete || data.verification_uri}
					</a>
					<p className="text-xs text-muted-foreground">
						{t("providers.xaiOauthWaiting")}
					</p>
				</div>
			) : (
				<Button
					className="w-full gap-2"
					onClick={begin}
					disabled={start.isPending || phase === "waiting"}
				>
					{start.isPending
						? t("providers.xaiOauthStarting")
						: t("providers.xaiOauthLogin")}
				</Button>
			)}
			{err && <p className="text-xs text-destructive">{err}</p>}
		</div>
	);
}

// Add/edit a per-user model.
//   • Editing → the classic field form (all provider fields, single save).
//   • Adding  → enter credentials, "Fetch models" from the provider API, then
//     multi-select the ones to add (bulk save). A collapsible manual-entry
//     fallback covers models the provider's API doesn't list.
function ProviderModelDialog({
	providers,
	initial,
	onClose,
}: {
	providers: ProviderType[];
	initial: ModelConfigItem | null;
	onClose: () => void;
}) {
	const { t } = useTranslation();
	const { save, saveBulk } = useModelMutations();
	const discover = useDiscoverModels();
	const editing = !!initial;
	// "xai_oauth" isn't its own selectable dropdown row — it's the same "xAI (Grok)"
	// entry as "xai" with a mode toggle, so an existing OAuth model normalizes its
	// dropdown selection to "xai" here and flips the toggle on instead.
	const [provider, setProvider] = useState<string>(
		initial?.provider === "xai_oauth"
			? "xai"
			: (initial?.provider ?? providers[0]?.id ?? "azure_openai"),
	);
	const [xaiOauthMode, setXaiOauthMode] = useState(
		initial?.provider === "xai_oauth",
	);
	// The dropdown only ever holds "xai"; the toggle decides which underlying
	// provider (and therefore which schema/fields/auth_flow) actually gets saved.
	const effectiveProvider =
		provider === "xai" && xaiOauthMode ? "xai_oauth" : provider;
	// Dropdown options hide "xai_oauth" — it's reached via the toggle, not a
	// second list entry.
	const providerOptions = providers.filter((p) => p.id !== "xai_oauth");
	const schema =
		providers.find((p) => p.id === effectiveProvider) ?? providers[0];
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
	// Discovery state — shared by add-mode (multi-select) and edit-mode (pick-one to
	// replace the current deployment).
	const [discovered, setDiscovered] = useState<DiscoveredModel[] | null>(null);
	const [selected, setSelected] = useState<Set<string>>(new Set());
	const [search, setSearch] = useState("");
	const [manualOpen, setManualOpen] = useState(false);
	// Edit-mode only: the discovered entry the user picked to switch this model to,
	// carried through to save so its label/capabilities update alongside deployment.
	const [switchedModel, setSwitchedModel] = useState<DiscoveredModel | null>(
		null,
	);
	// xai_oauth add-mode only: the refresh_token/expiry from a completed device-code
	// login, carried through to the final save-bulk call (the access_token itself
	// rides in `values.api_key`, same field a typed API key would use).
	const [oauthTokens, setOauthTokens] = useState<{
		refresh_token?: string;
		expires_at?: number;
	} | null>(null);
	const setField = (k: string, val: string) =>
		setValues((p) => ({ ...p, [k]: val }));

	// Credential fields for discovery = every provider field except the model's own
	// id/deployment (those come FROM the fetched list).
	const credFields = (schema?.fields ?? []).filter(
		(f) => f.key !== "id" && f.key !== "deployment",
	);
	const credEntry = () => {
		const entry: Record<string, unknown> = { provider: effectiveProvider };
		for (const f of credFields) {
			const v = (values[f.key] ?? "").trim();
			if (v) entry[f.key] = v;
		}
		// Editing: a masked/blank secret above can't be un-masked to resend, so let the
		// backend fall back to this model's own stored credentials for discovery.
		if (editing && initial?.id) entry.edit_id = initial.id;
		return entry;
	};

	const onFetch = () => {
		setErr(null);
		setDiscovered(null);
		setSelected(new Set());
		setSwitchedModel(null);
		discover.mutate(credEntry(), {
			onSuccess: (res) =>
				res.ok && res.models
					? setDiscovered(res.models)
					: setErr(res.error ?? t("providers.fetchFailed")),
			onError: () => setErr(t("providers.fetchFailed")),
		});
	};

	// xai_oauth device-code login just completed — populate the access_token into
	// the same `api_key` field a typed key would use, stash the refresh_token/expiry
	// for the eventual save, and fetch the catalog with it directly (NOT via
	// onFetch/credEntry — setValues hasn't re-rendered yet, so reading `values` here
	// would see the stale pre-login state).
	const onXaiAuthenticated = (tokens: {
		access_token: string;
		refresh_token?: string;
		expires_at?: number;
	}) => {
		setValues((p) => ({ ...p, api_key: tokens.access_token }));
		setOauthTokens({
			refresh_token: tokens.refresh_token,
			expires_at: tokens.expires_at,
		});
		setErr(null);
		setDiscovered(null);
		setSelected(new Set());
		discover.mutate(
			{ provider: effectiveProvider, api_key: tokens.access_token },
			{
				onSuccess: (res) =>
					res.ok && res.models
						? setDiscovered(res.models)
						: setErr(res.error ?? t("providers.fetchFailed")),
				onError: () => setErr(t("providers.fetchFailed")),
			},
		);
	};

	const toggle = (id: string) =>
		setSelected((s) => {
			const n = new Set(s);
			n.has(id) ? n.delete(id) : n.add(id);
			return n;
		});

	// Edit mode: picking a discovered model replaces THIS row's deployment (the id
	// stays put — it's the stable catalog key) instead of adding a new row.
	const pickForEdit = (m: DiscoveredModel) => {
		setSwitchedModel(m);
		setField("deployment", m.id);
	};

	const onAddSelected = () => {
		if (!selected.size) return;
		setErr(null);
		const entry = credEntry();
		// xai_oauth: the access_token is already in `values.api_key` (credEntry picks
		// it up like any other credential field), but the refresh_token/expiry aren't
		// part of the provider's visible field schema — carry them separately.
		if (oauthTokens?.refresh_token)
			entry.xai_refresh_token = oauthTokens.refresh_token;
		if (oauthTokens?.expires_at)
			entry.xai_token_expires_at = oauthTokens.expires_at;
		entry.ids = [...selected];
		const labels: Record<string, string> = {};
		const capabilities: Record<string, string[]> = {};
		for (const m of discovered ?? []) {
			if (!selected.has(m.id)) continue;
			if (m.label && m.label !== m.id) labels[m.id] = m.label;
			if (m.capabilities?.length) capabilities[m.id] = m.capabilities;
		}
		entry.labels = labels;
		entry.capabilities = capabilities;
		saveBulk.mutate(entry, {
			onSuccess: (res) => {
				const perModelErrors = Object.entries(res.errors ?? {});
				// Only auto-close when EVERY selected model saved cleanly — a bulk save can
				// partially succeed (e.g. one id collides), and the per-model reason lives in
				// res.errors, not a single res.error, so surface it instead of a generic message.
				if (res.ok && perModelErrors.length === 0) {
					onClose();
					return;
				}
				setErr(
					perModelErrors.length
						? perModelErrors.map(([id, msg]) => `${id}: ${msg}`).join("; ")
						: (res.error ?? t("providers.saveFailed")),
				);
			},
			onError: () => setErr(t("providers.saveFailed")),
		});
	};

	// Manual entry (edit mode, or the add-mode fallback): the classic full form.
	const onSaveManual = () => {
		const entry: Record<string, unknown> = { provider: effectiveProvider };
		for (const f of schema?.fields ?? []) {
			const val = (values[f.key] ?? "").trim();
			if (val) entry[f.key] = val;
		}
		if (!entry.id) {
			setErr(t("providers.idRequired"));
			return;
		}
		// Switched to a different model via the fetch/pick list: carry its label +
		// capabilities along with the deployment change already reflected in `values`.
		if (switchedModel) {
			if (switchedModel.label && switchedModel.label !== switchedModel.id) {
				entry.label = switchedModel.label;
			}
			if (switchedModel.capabilities?.length) {
				entry.capabilities = switchedModel.capabilities;
			}
		}
		setErr(null);
		save.mutate(entry, {
			onSuccess: (res) =>
				res?.ok === false
					? setErr(res.error ?? t("providers.saveFailed"))
					: onClose(),
			onError: () => setErr(t("providers.saveFailed")),
		});
	};

	const q = search.trim().toLowerCase();
	const filtered = (discovered ?? []).filter(
		(m) =>
			!q ||
			m.id.toLowerCase().includes(q) ||
			(m.label ?? "").toLowerCase().includes(q),
	);

	const renderField = (f: ProviderType["fields"][number]) => (
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
						? t("providers.unchanged")
						: f.placeholder
				}
			/>
		</div>
	);

	return (
		<Dialog open onOpenChange={(o) => !o && onClose()}>
			<DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto sm:max-w-2xl">
				<DialogHeader>
					<DialogTitle>
						{editing
							? t("providers.editTitle", { id: initial?.id })
							: t("providers.addTitle")}
					</DialogTitle>
				</DialogHeader>
				<div className="space-y-3">
					<div className="space-y-1.5">
						<Label htmlFor="prov">{t("providers.provider")}</Label>
						<Select
							value={provider}
							onValueChange={(v) => {
								if (!v) return;
								setProvider(v);
								if (v !== "xai") setXaiOauthMode(false);
							}}
						>
							<SelectTrigger id="prov" className="w-full">
								<SelectValue />
							</SelectTrigger>
							{/* alignItemWithTrigger (the base default) centers the SELECTED item on
							    the trigger, native-select style — with 5 providers, whichever one is
							    selected changes how many options render above vs. below, so the list
							    appears to jump to a different position depending on context (e.g. Edit
							    mode, where the selected provider often isn't first). Anchoring below
							    the trigger instead keeps it in the same place every time. */}
							<SelectContent alignItemWithTrigger={false}>
								{providerOptions.map((p) => (
									<SelectItem key={p.id} value={p.id}>
										{p.label}
									</SelectItem>
								))}
							</SelectContent>
						</Select>
					</div>

					{/* xAI's OAuth device-code login is a mode of the same provider, not a
					    separate catalog entry — toggling it swaps the schema/fields (and, in
					    add-mode, the credential-form vs. login-widget view) without a second
					    "xAI Grok OAuth" row in the dropdown. */}
					{provider === "xai" && (
						<div className="flex items-center justify-between gap-3 rounded-md border p-3">
							<div className="space-y-0.5">
								<Label htmlFor="xai-oauth-toggle">
									{t("providers.xaiUseOauth")}
								</Label>
								<p className="text-xs text-muted-foreground">
									{t("providers.xaiUseOauthHint")}
								</p>
							</div>
							<Switch
								id="xai-oauth-toggle"
								checked={xaiOauthMode}
								onCheckedChange={setXaiOauthMode}
							/>
						</div>
					)}

					{editing ? (
						// ── Edit: classic full form + optional fetch-and-switch ────────
						<>
							{schema?.fields.map(renderField)}
							<Button
								variant="outline"
								className="w-full gap-2"
								onClick={onFetch}
								disabled={discover.isPending}
							>
								<Search className="size-4" />
								{discover.isPending
									? t("providers.fetching")
									: t("providers.fetchModels")}
							</Button>

							{discovered && (
								<div className="space-y-2">
									<Input
										value={search}
										onChange={(e) => setSearch(e.target.value)}
										placeholder={t("providers.searchModels")}
									/>
									<div className="max-h-64 space-y-0.5 overflow-y-auto rounded-md border p-1">
										{filtered.length === 0 ? (
											<p className="px-2 py-3 text-center text-xs text-muted-foreground">
												{t("providers.noModelsFound")}
											</p>
										) : (
											filtered.map((m) => (
												<DiscoveredRow
													key={m.id}
													model={m}
													checked={switchedModel?.id === m.id}
													onToggle={() => pickForEdit(m)}
													capabilitiesLabel={t("providers.capabilities")}
												/>
											))
										)}
									</div>
								</div>
							)}

							{err && <p className="text-xs text-destructive">{err}</p>}
							<div className="flex justify-end gap-2">
								<Button variant="ghost" onClick={onClose}>
									{t("common.cancel")}
								</Button>
								<Button onClick={onSaveManual} disabled={save.isPending}>
									{save.isPending ? t("common.saving") : t("common.save")}
								</Button>
							</div>
						</>
					) : (
						// ── Add: fetch → multi-select ────────────────────────────────
						<>
							{schema?.auth_flow === "xai_device_code" ? (
								<XaiOauthLogin onAuthenticated={onXaiAuthenticated} />
							) : (
								<>
									{credFields.map(renderField)}
									<Button
										variant="outline"
										className="w-full gap-2"
										onClick={onFetch}
										disabled={discover.isPending}
									>
										<Search className="size-4" />
										{discover.isPending
											? t("providers.fetching")
											: t("providers.fetchModels")}
									</Button>
								</>
							)}

							{discovered && (
								<div className="space-y-2">
									<Input
										value={search}
										onChange={(e) => setSearch(e.target.value)}
										placeholder={t("providers.searchModels")}
									/>
									<div className="max-h-64 space-y-0.5 overflow-y-auto rounded-md border p-1">
										{filtered.length === 0 ? (
											<p className="px-2 py-3 text-center text-xs text-muted-foreground">
												{t("providers.noModelsFound")}
											</p>
										) : (
											filtered.map((m) => (
												<DiscoveredRow
													key={m.id}
													model={m}
													checked={selected.has(m.id)}
													onToggle={() => toggle(m.id)}
													capabilitiesLabel={t("providers.capabilities")}
												/>
											))
										)}
									</div>
								</div>
							)}

							{/* Fallback: type a model id by hand (for anything the API omits). */}
							<Collapsible open={manualOpen} onOpenChange={setManualOpen}>
								<CollapsibleTrigger className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
									<ChevronDown
										className={cn(
											"size-3.5 transition-transform",
											manualOpen && "rotate-180",
										)}
									/>
									{t("providers.enterManually")}
								</CollapsibleTrigger>
								<CollapsibleContent className="space-y-3 pt-2">
									{schema?.fields.map(renderField)}
									<div className="flex justify-end">
										<Button
											size="sm"
											variant="secondary"
											onClick={onSaveManual}
											disabled={save.isPending}
										>
											{save.isPending ? t("common.saving") : t("common.save")}
										</Button>
									</div>
								</CollapsibleContent>
							</Collapsible>

							{err && <p className="text-xs text-destructive">{err}</p>}
							<div className="flex justify-end gap-2">
								<Button variant="ghost" onClick={onClose}>
									{t("common.cancel")}
								</Button>
								<Button
									onClick={onAddSelected}
									disabled={saveBulk.isPending || selected.size === 0}
								>
									{saveBulk.isPending
										? t("common.saving")
										: t("providers.addSelected", { count: selected.size })}
								</Button>
							</div>
						</>
					)}
				</div>
			</DialogContent>
		</Dialog>
	);
}

export function ProvidersPanel() {
	const { t } = useTranslation();
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
			title={t("providers.title")}
			description={t("providers.subtitle")}
			maxWidthClassName="max-w-5xl"
		>
			<div className="flex justify-end">
				<Button size="sm" variant="outline" onClick={openNew}>
					<Plus className="size-3.5" /> {t("providers.addModel")}
				</Button>
			</div>
			{isLoading && (
				<p className="text-sm text-muted-foreground">{t("common.loading")}</p>
			)}
			{models.map((m) => {
				const tr = testResults[m.id];
				return (
					<Card
						key={`${m.scope}-${m.id}`}
						className="flex-row items-center justify-between gap-3 p-3"
					>
						<div className="min-w-0">
							<div className="flex flex-wrap items-center gap-2">
								<span className="break-all font-mono text-sm font-medium">
									{m.id}
								</span>
								<Badge variant="outline" className="text-[10px]">
									{m.provider}
								</Badge>
								<Badge variant="outline" className="text-[10px]">
									{m.scope}
								</Badge>
								{tr && (
									<Badge
										variant={tr.standard.ok ? "default" : "destructive"}
										className="text-[10px]"
									>
										{tr.standard.ok
											? t("providers.testOk")
											: t("providers.testFail")}
									</Badge>
								)}
								{/* Reasoning support is reported by the live Test probe (like
								    "test ok"), not the static config — only shown once tested. */}
								{tr?.standard.ok && (
									<Badge
										variant={tr.reasoning.supported ? "secondary" : "outline"}
										className="text-[10px]"
									>
										{tr.reasoning.supported
											? t("providers.reasoning")
											: t("providers.noReasoning")}
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
								{testing === m.id
									? t("providers.testing")
									: t("providers.test")}
							</Button>
							{m.editable ? (
								<>
									<Button size="sm" variant="ghost" onClick={() => openEdit(m)}>
										{t("common.edit")}
									</Button>
									<Button
										size="sm"
										variant="ghost"
										onClick={() => remove.mutate(m.id)}
									>
										{t("common.delete")}
									</Button>
								</>
							) : (
								<Badge variant="secondary" className="text-[10px]">
									{t("common.readOnly")}
								</Badge>
							)}
						</div>
					</Card>
				);
			})}
			{dialogOpen && providers.length > 0 && (
				<ProviderModelDialog
					key={editTarget?.id ?? NEW_ITEM}
					providers={providers}
					initial={editTarget}
					onClose={() => setDialogOpen(false)}
				/>
			)}
		</PanelLayout>
	);
}
