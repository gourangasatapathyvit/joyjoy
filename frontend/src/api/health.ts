import { useQuery } from "@tanstack/react-query";
import { http } from "@/api/client";

export interface HealthResponse {
	status?: string;
	state?: string;
	gateway_state?: string;
	env?: string;
}

// Backend heartbeat — polls /v1/health on an interval so the UI can reflect the
// connection as connecting → idle (alive) → offline (unreachable). `retry:false`
// makes a dropped backend surface as an error promptly instead of retrying
// silently; a short refetchInterval keeps the indicator live.
export function useHealth() {
	return useQuery({
		queryKey: ["health"],
		queryFn: () => http<HealthResponse>("/v1/health"),
		refetchInterval: 20000,
		refetchIntervalInBackground: true,
		refetchOnWindowFocus: true,
		retry: false,
		staleTime: 10000,
	});
}
