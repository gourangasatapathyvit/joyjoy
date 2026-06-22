import type { ReactNode } from "react";

// Labelled card wrapper used by the settings panes.
export function Field({
	label,
	desc,
	children,
}: {
	label: string;
	desc?: string;
	children: ReactNode;
}) {
	return (
		<div className="rounded-xl border border-border bg-sidebar p-4">
			<div className="mb-2 text-xs font-medium text-muted-foreground">
				{label}
			</div>
			{children}
			{desc && <p className="mt-2 text-[11px] text-muted-foreground">{desc}</p>}
		</div>
	);
}
