import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "@/App";
import { Toaster } from "@/components/ui/sonner";
import { Providers } from "@/providers";
import "./index.css";

createRoot(document.getElementById("root")!).render(
	<StrictMode>
		<Providers>
			<App />
			<Toaster />
		</Providers>
	</StrictMode>,
);
