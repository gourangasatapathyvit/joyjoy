import { useQuery } from "@tanstack/react-query";
import { http } from "@/api/client";

// Server capability advertisement (GET /v1/capabilities). `sandbox.mount_path`
// lets the client map mount-prefixed media paths to workspace-relative tree paths.
export interface Capabilities {
	name: string;
	features?: Record<string, boolean>;
	sandbox?: { enabled: boolean; mount_path: string };
}

// Effectively static per server build — cache for the session.
export function useCapabilities() {
	return useQuery({
		queryKey: ["capabilities"],
		queryFn: () => http<Capabilities>("/v1/capabilities"),
		staleTime: Number.POSITIVE_INFINITY,
	});
}
