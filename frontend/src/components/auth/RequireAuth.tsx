import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useMe } from "@/api/auth";

// Route guard backed by the real session: GET /v1/auth/me. While it's resolving
// we render nothing; a 401 (not signed in) bounces to /signin, remembering where
// the visitor was headed so sign-in can send them back.
export function RequireAuth({ children }: { children: ReactNode }) {
	const { data, isLoading, isError } = useMe();
	const location = useLocation();
	if (isLoading) return null;
	if (isError || !data) {
		return <Navigate to="/signin" replace state={{ from: location }} />;
	}
	return <>{children}</>;
}
