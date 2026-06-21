import { BrowserRouter, Route, Routes } from "react-router-dom";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { AppShell } from "@/components/layout/AppShell";
import { AuthPage } from "@/routes/AuthPage";
import { ChatPage } from "@/routes/ChatPage";
import { McpPanel } from "@/routes/McpPanel";
import { MemoryPanel } from "@/routes/MemoryPanel";
import { SettingsPage } from "@/routes/SettingsPage";
import { SkillsPanel } from "@/routes/SkillsPanel";

export default function App() {
	return (
		<BrowserRouter>
			<Routes>
				<Route path="/signin" element={<AuthPage />} />
				<Route
					element={
						<RequireAuth>
							<AppShell />
						</RequireAuth>
					}
				>
					<Route path="/" element={<ChatPage />} />
					<Route path="/session/:sessionId" element={<ChatPage />} />
					<Route path="/mcp" element={<McpPanel />} />
					<Route path="/skills" element={<SkillsPanel />} />
					<Route path="/memory" element={<MemoryPanel />} />
					<Route path="/settings" element={<SettingsPage />} />
				</Route>
			</Routes>
		</BrowserRouter>
	);
}
