import { Brain, MessageSquare, Plug, Sparkles } from "lucide-react";
import type { ComponentType } from "react";

export interface RailTab {
	key: string;
	to: string;
	label: string;
	icon: ComponentType<{ className?: string; strokeWidth?: number }>;
	end: boolean;
}

// The reorderable left-rail nav tabs (shared by AppShell + the Settings
// reorder UI). Workspace + Settings are fixed at the bottom, not part of this.
export const RAIL_TABS: RailTab[] = [
	{ key: "chat", to: "/", label: "Chat", icon: MessageSquare, end: true },
	{ key: "mcp", to: "/mcp", label: "MCP", icon: Plug, end: false },
	{ key: "skills", to: "/skills", label: "Skills", icon: Sparkles, end: false },
	{ key: "memory", to: "/memory", label: "Memory", icon: Brain, end: false },
];

export const DEFAULT_TAB_ORDER = RAIL_TABS.map((t) => t.key);

// Resolve a saved key-order into RailTab[]. Unknown keys are skipped; tabs not
// in the saved order (e.g. newly added) are appended so nothing disappears.
export function orderTabs(order: string[] | undefined | null): RailTab[] {
	if (!order || order.length === 0) return RAIL_TABS;
	const byKey = new Map(RAIL_TABS.map((t) => [t.key, t]));
	const out: RailTab[] = [];
	for (const k of order) {
		const t = byKey.get(k);
		if (t) {
			out.push(t);
			byKey.delete(k);
		}
	}
	for (const t of byKey.values()) out.push(t);
	return out;
}
