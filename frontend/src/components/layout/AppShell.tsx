import { Brain, MessageSquare, Plug, Server, Sparkles } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { cn } from "@/lib/utils";

const NAV = [
	{ to: "/", label: "Chat", icon: MessageSquare, end: true },
	{ to: "/mcp", label: "MCP", icon: Plug, end: false },
	{ to: "/skills", label: "Skills", icon: Sparkles, end: false },
	{ to: "/providers", label: "Providers", icon: Server, end: false },
	{ to: "/memory", label: "Memory", icon: Brain, end: false },
];

// Narrow icon rail (webui style): 48px wide, gold-tinted active state with a
// left accent bar. The per-view content (chat sessions / panels) lives in main.
export function AppShell() {
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
			</nav>
			<main className="flex min-w-0 flex-1 flex-col">
				<Outlet />
			</main>
		</div>
	);
}
