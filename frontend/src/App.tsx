import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { ChatPage } from "@/routes/ChatPage";
import { McpPanel } from "@/routes/McpPanel";
import { MemoryPanel } from "@/routes/MemoryPanel";
import { ProvidersPanel } from "@/routes/ProvidersPanel";
import { SkillsPanel } from "@/routes/SkillsPanel";

export default function App() {
	return (
		<BrowserRouter>
			<Routes>
				<Route element={<AppShell />}>
					<Route path="/" element={<ChatPage />} />
					<Route path="/session/:sessionId" element={<ChatPage />} />
					<Route path="/mcp" element={<McpPanel />} />
					<Route path="/skills" element={<SkillsPanel />} />
					<Route path="/providers" element={<ProvidersPanel />} />
					<Route path="/memory" element={<MemoryPanel />} />
				</Route>
			</Routes>
		</BrowserRouter>
	);
}
