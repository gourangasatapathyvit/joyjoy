import { useTranslation } from "react-i18next";
import { useHealth } from "@/api/health";
import {
	DotMatrix,
	type DotMatrixState,
} from "@/components/assistant-ui/dot-matrix";
import { cn } from "@/lib/utils";

// Backend connection indicator for the nav rail, driven by the heartbeat. Unlike
// the in-chat matrices (which inherit the theme color), this one is explicitly
// status-colored: connected = green, connecting = amber, offline = red.
export function ConnectionStatus() {
	const { t } = useTranslation();
	const q = useHealth();

	const alive =
		q.isSuccess && (q.data?.status === "ok" || q.data?.state === "alive");
	const status: { state: DotMatrixState; key: string; color: string } =
		q.isError
			? { state: "offline", key: "offline", color: "text-red-500" }
			: alive
				? { state: "idle", key: "connected", color: "text-emerald-500" }
				: { state: "connecting", key: "connecting", color: "text-amber-500" };
	const label = t(`connection.${status.key}`);

	return (
		<div title={label} className="flex size-9 items-center justify-center">
			<DotMatrix
				state={status.state}
				className={cn("size-5", status.color)}
				label={label}
			/>
		</div>
	);
}
