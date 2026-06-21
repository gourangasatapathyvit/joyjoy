import type { ReactNode } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";

// Shared chrome for the side panels: a sticky title header + a scrollable body.
export function PanelLayout({
	title,
	description,
	children,
}: {
	title: string;
	description?: string;
	children: ReactNode;
}) {
	return (
		<div className="flex min-h-0 flex-1 flex-col">
			<div className="border-b border-border px-6 py-3">
				<h1 className="font-heading text-lg font-semibold text-foreground">
					{title}
				</h1>
				{description && (
					<p className="text-xs text-muted-foreground">{description}</p>
				)}
			</div>
			<ScrollArea className="min-h-0 flex-1">
				<div className="mx-auto max-w-3xl space-y-6 p-6">{children}</div>
			</ScrollArea>
		</div>
	);
}
