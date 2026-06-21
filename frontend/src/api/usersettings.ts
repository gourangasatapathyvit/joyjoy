import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { http } from "@/api/client";

export interface UiSettings {
	sidebar_order?: string[];
	display_name?: string;
	email?: string;
}

const KEY = ["ui-settings"];

export const uiSettingsApi = {
	get: () => http<UiSettings>("/v1/settings/ui"),
	put: (data: UiSettings) =>
		http<{ ok: boolean }>("/v1/settings/ui", {
			method: "PUT",
			body: JSON.stringify(data),
		}),
};

export function useUiSettings() {
	return useQuery({ queryKey: KEY, queryFn: uiSettingsApi.get });
}

export function useUpdateUiSettings() {
	const qc = useQueryClient();
	return useMutation({
		// PUT replaces the whole ui.json, so merge the partial update with the
		// current settings before sending — otherwise saving the profile would
		// wipe sidebar_order (and vice-versa).
		mutationFn: (data: UiSettings) =>
			uiSettingsApi.put({
				...(qc.getQueryData<UiSettings>(KEY) ?? {}),
				...data,
			}),
		// Optimistic: update the cache immediately so the rail reorders without a
		// refetch round-trip; roll back on error.
		onMutate: async (data) => {
			await qc.cancelQueries({ queryKey: KEY });
			const prev = qc.getQueryData<UiSettings>(KEY);
			qc.setQueryData<UiSettings>(KEY, { ...prev, ...data });
			return { prev };
		},
		onError: (_e, _d, ctx) => {
			if (ctx?.prev) qc.setQueryData(KEY, ctx.prev);
		},
		onSettled: () => qc.invalidateQueries({ queryKey: KEY }),
	});
}
