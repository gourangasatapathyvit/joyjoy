import { Plus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMcpMutations, useMcpServers, useMcpTools } from "@/api/queries";
import type { McpServer, McpStatus } from "@/api/types";
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
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { NEW_ITEM } from "@/lib/constants";

const statusVariant = (
	s: McpStatus,
): "default" | "secondary" | "destructive" =>
	s === "active"
		? "default"
		: s === "invalid_config"
			? "destructive"
			: "secondary";

const parseLines = (t: string) =>
	t
		.split("\n")
		.map((s) => s.trim())
		.filter(Boolean);
const parseKV = (t: string): Record<string, string> => {
	const out: Record<string, string> = {};
	for (const line of t.split("\n")) {
		const i = line.indexOf("=");
		if (i > 0) out[line.slice(0, i).trim()] = line.slice(i + 1).trim();
	}
	return out;
};

// Add/edit a per-user MCP server. The GET endpoint never returns env/headers
// (secrets), so on edit those start blank — re-enter to change them.
function McpServerDialog({
	initial,
	onClose,
}: {
	initial: McpServer | null;
	onClose: () => void;
}) {
	const { t } = useTranslation();
	const { save } = useMcpMutations();
	const editing = !!initial;
	const [name, setName] = useState(initial?.name ?? "");
	const [transport, setTransport] = useState<"stdio" | "http">(
		initial?.url ? "http" : "stdio",
	);
	const [command, setCommand] = useState(initial?.command ?? "");
	const [argsText, setArgsText] = useState((initial?.args ?? []).join("\n"));
	const [url, setUrl] = useState(initial?.url ?? "");
	const [envText, setEnvText] = useState("");
	const [headersText, setHeadersText] = useState("");
	const [err, setErr] = useState<string | null>(null);

	const valid = Boolean(
		name.trim() && (transport === "stdio" ? command.trim() : url.trim()),
	);

	const onSave = () => {
		if (!valid) return;
		const cfg: Record<string, unknown> = {
			transport: transport === "http" ? "streamable_http" : "stdio",
		};
		if (transport === "stdio") {
			cfg.command = command.trim();
			const a = parseLines(argsText);
			if (a.length) cfg.args = a;
			const env = parseKV(envText);
			if (Object.keys(env).length) cfg.env = env;
		} else {
			cfg.url = url.trim();
			const h = parseKV(headersText);
			if (Object.keys(h).length) cfg.headers = h;
		}
		setErr(null);
		save.mutate(
			{ name: name.trim(), cfg },
			{
				onSuccess: (res) =>
					res?.ok === false
						? setErr(res.error ?? t("providers.saveFailed"))
						: onClose(),
				onError: () => setErr(t("providers.saveFailed")),
			},
		);
	};

	return (
		<Dialog open onOpenChange={(o) => !o && onClose()}>
			<DialogContent className="max-w-lg">
				<DialogHeader>
					<DialogTitle>
						{editing
							? t("mcp.editTitle", { name: initial?.name })
							: t("mcp.addTitle")}
					</DialogTitle>
				</DialogHeader>
				<div className="space-y-3">
					<div className="space-y-1.5">
						<Label htmlFor="mcp-name">{t("mcp.name")}</Label>
						<Input
							id="mcp-name"
							value={name}
							disabled={editing}
							onChange={(e) => setName(e.target.value)}
							placeholder="my-server"
						/>
					</div>
					<div className="space-y-1.5">
						<Label htmlFor="mcp-transport">{t("mcp.transport")}</Label>
						<Select
							value={transport}
							onValueChange={(v) => v && setTransport(v as "stdio" | "http")}
						>
							<SelectTrigger id="mcp-transport">
								<SelectValue />
							</SelectTrigger>
							<SelectContent>
								<SelectItem value="stdio">{t("mcp.transportStdio")}</SelectItem>
								<SelectItem value="http">{t("mcp.transportHttp")}</SelectItem>
							</SelectContent>
						</Select>
					</div>
					{transport === "stdio" ? (
						<>
							<div className="space-y-1.5">
								<Label htmlFor="mcp-cmd">{t("mcp.command")}</Label>
								<Input
									id="mcp-cmd"
									value={command}
									onChange={(e) => setCommand(e.target.value)}
									placeholder="uvx"
								/>
							</div>
							<div className="space-y-1.5">
								<Label htmlFor="mcp-args">{t("mcp.argsField")}</Label>
								<Textarea
									id="mcp-args"
									value={argsText}
									onChange={(e) => setArgsText(e.target.value)}
									rows={3}
									placeholder="duckduckgo-mcp-server"
									className="font-mono text-xs"
								/>
							</div>
							<div className="space-y-1.5">
								<Label htmlFor="mcp-env">{t("mcp.env")}</Label>
								<Textarea
									id="mcp-env"
									value={envText}
									onChange={(e) => setEnvText(e.target.value)}
									rows={2}
									placeholder="API_KEY=..."
									className="font-mono text-xs"
								/>
							</div>
						</>
					) : (
						<>
							<div className="space-y-1.5">
								<Label htmlFor="mcp-url">{t("mcp.url")}</Label>
								<Input
									id="mcp-url"
									value={url}
									onChange={(e) => setUrl(e.target.value)}
									placeholder="http://localhost:9000/mcp"
								/>
							</div>
							<div className="space-y-1.5">
								<Label htmlFor="mcp-headers">{t("mcp.headers")}</Label>
								<Textarea
									id="mcp-headers"
									value={headersText}
									onChange={(e) => setHeadersText(e.target.value)}
									rows={2}
									className="font-mono text-xs"
								/>
							</div>
						</>
					)}
					{err && <p className="text-xs text-destructive">{err}</p>}
					<div className="flex justify-end gap-2 pt-1">
						<Button variant="ghost" onClick={onClose}>
							{t("common.cancel")}
						</Button>
						<Button onClick={onSave} disabled={!valid || save.isPending}>
							{save.isPending ? t("common.saving") : t("common.save")}
						</Button>
					</div>
				</div>
			</DialogContent>
		</Dialog>
	);
}

export function McpPanel() {
	const { t } = useTranslation();
	const { data: serverData, isLoading } = useMcpServers();
	const { data: toolData } = useMcpTools();
	const { toggle, remove } = useMcpMutations();
	const servers = serverData?.servers ?? [];
	const tools = toolData?.tools ?? [];

	const [dialogOpen, setDialogOpen] = useState(false);
	const [editTarget, setEditTarget] = useState<McpServer | null>(null);
	const openNew = () => {
		setEditTarget(null);
		setDialogOpen(true);
	};
	const openEdit = (s: McpServer) => {
		setEditTarget(s);
		setDialogOpen(true);
	};

	return (
		<PanelLayout title={t("mcp.title")} description={t("mcp.subtitle")}>
			<section className="space-y-2">
				<div className="flex items-center justify-between">
					<h2 className="text-sm font-medium text-muted-foreground">
						{t("mcp.servers")}
					</h2>
					<Button size="sm" variant="outline" onClick={openNew}>
						<Plus className="size-3.5" /> {t("mcp.addServer")}
					</Button>
				</div>
				{isLoading && (
					<p className="text-sm text-muted-foreground">{t("common.loading")}</p>
				)}
				{!isLoading && servers.length === 0 && (
					<p className="text-sm text-muted-foreground">{t("mcp.noServers")}</p>
				)}
				{servers.map((s) => (
					<Card
						key={`${s.scope}-${s.name}`}
						className="flex-row items-center justify-between gap-3 p-3"
					>
						<div className="min-w-0">
							<div className="flex flex-wrap items-center gap-2">
								<span className="font-medium">{s.name}</span>
								<Badge variant="outline" className="text-[10px]">
									{s.scope}
								</Badge>
								<Badge
									variant={statusVariant(s.status)}
									className="text-[10px]"
								>
									{s.status}
								</Badge>
								{s.tool_count != null && (
									<span className="text-xs text-muted-foreground">
										{s.tool_count} {t("mcp.toolsSuffix")}
									</span>
								)}
							</div>
							<p className="truncate text-xs text-muted-foreground">
								{s.url || s.command || s.transport}
							</p>
						</div>
						{s.scope === "user" ? (
							<div className="flex shrink-0 items-center gap-2">
								<Switch
									checked={s.enabled}
									onCheckedChange={(enabled) =>
										toggle.mutate({ name: s.name, enabled })
									}
								/>
								<Button size="sm" variant="ghost" onClick={() => openEdit(s)}>
									{t("common.edit")}
								</Button>
								<Button
									size="sm"
									variant="ghost"
									onClick={() => remove.mutate(s.name)}
								>
									{t("common.delete")}
								</Button>
							</div>
						) : (
							<Badge variant="secondary" className="shrink-0 text-[10px]">
								{t("common.readOnly")}
							</Badge>
						)}
					</Card>
				))}
			</section>

			<section className="space-y-2">
				<h2 className="text-sm font-medium text-muted-foreground">
					{t("mcp.tools")} ({tools.length})
				</h2>
				{tools.map((tool) => (
					<Card key={`${tool.server}-${tool.name}`} className="gap-1 p-3">
						<div className="flex flex-wrap items-center gap-2">
							<span className="font-mono text-sm font-medium">{tool.name}</span>
							<Badge variant="outline" className="text-[10px]">
								{tool.server}
							</Badge>
						</div>
						{tool.description && (
							<p className="text-xs text-muted-foreground">
								{tool.description}
							</p>
						)}
						{tool.schema_summary?.length > 0 && (
							<p className="text-[11px] text-muted-foreground">
								{t("mcp.args")}{" "}
								{tool.schema_summary
									.map((p) => `${p.name}${p.required ? "*" : ""}`)
									.join(", ")}
							</p>
						)}
					</Card>
				))}
			</section>

			{dialogOpen && (
				<McpServerDialog
					key={editTarget?.name ?? NEW_ITEM}
					initial={editTarget}
					onClose={() => setDialogOpen(false)}
				/>
			)}
		</PanelLayout>
	);
}
