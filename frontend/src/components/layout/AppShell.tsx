import {
	Brain,
	FolderTree,
	MessageSquare,
	Plug,
	Server,
	Sparkles,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { WorkspaceDock } from "@/components/chat/WorkspaceDock";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/store/chat";

const NAV = [
	{ to: "/", label: "Chat", icon: MessageSquare, end: true },
	{ to: "/mcp", label: "MCP", icon: Plug, end: false },
	{ to: "/skills", label: "Skills", icon: Sparkles, end: false },
	{ to: "/providers", label: "Providers", icon: Server, end: false },
	{ to: "/memory", label: "Memory", icon: Brain, end: false },
];

// Narrow icon rail (webui style): 48px wide, gold-tinted active state. The
// workspace dock toggle lives at the bottom so it's reachable on every screen;
// the dock itself is rendered here (global) and self-hides when closed.
export function AppShell() {
	const workspaceOpen = useChatStore((s) => s.workspaceOpen);
	const toggleWorkspace = useChatStore((s) => s.toggleWorkspace);

	return (
		<div className="flex h-svh w-full bg-background text-foreground">
			<nav className="flex w-12 shrink-0 flex-col items-center gap-1 border-r border-border bg-sidebar py-2">
				<img src="/joyjoy-icon.svg" alt="joyjoy" className="mb-1 size-7" />
				{NAV.map(({ to, label, icon: Icon, end }) => (
					<NavLink
						key={to}
						to={to}
						end={end}
						title={label}
						className={({ isActive }) =>
							cn(
								"group relative flex size-9 items-center justify-center rounded-lg transition-colors",
								isActive
									? "bg-primary/10 text-primary"
									: "text-muted-foreground hover:bg-foreground/5 hover:text-foreground",
							)
						}
					>
						{({ isActive }) => (
							<>
								{isActive && (
									<span className="absolute -left-1.5 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r bg-primary" />
								)}
								<Icon className="size-5" strokeWidth={1.5} />
							</>
						)}
					</NavLink>
				))}
				<div className="flex-1" />
				<button
					type="button"
					onClick={toggleWorkspace}
					title="Workspace"
					aria-pressed={workspaceOpen}
					className={cn(
						"group relative flex size-9 items-center justify-center rounded-lg transition-colors",
						workspaceOpen
							? "bg-primary/10 text-primary"
							: "text-muted-foreground hover:bg-foreground/5 hover:text-foreground",
					)}
				>
					{workspaceOpen && (
						<span className="absolute -left-1.5 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r bg-primary" />
					)}
					<FolderTree className="size-5" strokeWidth={1.5} />
				</button>
			</nav>
			<main className="flex min-w-0 flex-1 flex-col">
				<Outlet />
			</main>
			<WorkspaceDock />
		</div>
	);
}
