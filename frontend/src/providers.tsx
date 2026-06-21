import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import type { ReactNode } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";

const queryClient = new QueryClient({
	defaultOptions: {
		queries: { staleTime: 30_000, refetchOnWindowFocus: false },
	},
});

// App-wide providers: server-state cache (TanStack Query), theme (next-themes,
// defaulting to joyjoy's signature dark navy+gold), and shadcn tooltips.
export function Providers({ children }: { children: ReactNode }) {
	return (
		<QueryClientProvider client={queryClient}>
			<ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
				<TooltipProvider>{children}</TooltipProvider>
			</ThemeProvider>
		</QueryClientProvider>
	);
}
