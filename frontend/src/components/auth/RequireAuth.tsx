import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuthStore } from "@/store/auth";

// Route guard: unauthenticated visitors are bounced to /signin, remembering where
// they were headed so sign-in can send them back.
export function RequireAuth({ children }: { children: ReactNode }) {
	const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
	const location = useLocation();
	if (!isAuthenticated) {
		return <Navigate to="/signin" replace state={{ from: location }} />;
	}
	return <>{children}</>;
}
