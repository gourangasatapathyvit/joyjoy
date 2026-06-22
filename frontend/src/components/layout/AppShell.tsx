import {
	closestCenter,
	DndContext,
	type DragEndEvent,
	PointerSensor,
	useSensor,
	useSensors,
} from "@dnd-kit/core";
import {
	arrayMove,
	SortableContext,
	useSortable,
	verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { FolderTree, Settings } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, Outlet } from "react-router-dom";
import { useUiSettings, useUpdateUiSettings } from "@/api/usersettings";
import { WorkspaceDock } from "@/components/chat/WorkspaceDock";
import { PrefsSync } from "@/components/PrefsSync";
import { orderTabs, type RailTab } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/store/chat";

const railLink = ({ isActive }: { isActive: boolean }) =>
	cn(
		"group relative flex size-9 items-center justify-center rounded-lg transition-colors",
		isActive
			? "bg-primary/10 text-primary"
			: "text-muted-foreground hover:bg-foreground/5 hover:text-foreground",
	);

function ActiveBar() {
	return (
		<span className="absolute -left-1.5 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r bg-primary" />
	);
}

// A rail tab that's directly drag-reorderable. PointerSensor's distance
// activation means a tap navigates (NavLink) while a drag past the threshold
// reorders — so the icons stay clickable links AND draggable handles at once.
function SortableRailTab({ tab }: { tab: RailTab }) {
	const { t } = useTranslation();
	const {
		attributes,
		listeners,
		setNodeRef,
		transform,
		transition,
		isDragging,
	} = useSortable({ id: tab.key });
	const Icon = tab.icon;
	return (
		<NavLink
			ref={setNodeRef}
			to={tab.to}
			end={tab.end}
			title={t(`nav.${tab.key}`)}
			style={{ transform: CSS.Transform.toString(transform), transition }}
			className={({ isActive }) =>
				cn(
					railLink({ isActive }),
					"touch-none",
					isDragging && "z-10 opacity-70 ring-1 ring-primary/40",
				)
			}
			{...attributes}
			{...listeners}
		>
			{({ isActive }) => (
				<>
					{isActive && <ActiveBar />}
					<Icon className="size-5" strokeWidth={1.5} />
				</>
			)}
		</NavLink>
	);
}

// Narrow icon rail (webui style). The logo links home; the nav tabs render in the
// user's saved order and are drag-reorderable in place (persisted server-side).
// Workspace toggle + Settings sit at the bottom; the workspace dock is global here.
export function AppShell() {
	const { t } = useTranslation();
	const workspaceOpen = useChatStore((s) => s.workspaceOpen);
	const toggleWorkspace = useChatStore((s) => s.toggleWorkspace);
	const { data: ui } = useUiSettings();
	const update = useUpdateUiSettings();
	const tabs = orderTabs(ui?.sidebar_order);
	const sensors = useSensors(
		useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
	);

	const onDragEnd = (e: DragEndEvent) => {
		const { active, over } = e;
		if (!over || active.id === over.id) return;
		const ids = tabs.map((t) => t.key);
		const next = arrayMove(
			ids,
			ids.indexOf(String(active.id)),
			ids.indexOf(String(over.id)),
		);
		update.mutate({ sidebar_order: next });
	};

	return (
		<div className="flex h-svh w-full bg-background text-foreground">
			<PrefsSync />
			<nav className="flex w-12 shrink-0 flex-col items-center gap-1 border-r border-border bg-sidebar py-2">
				<Link
					to="/"
					title={t("nav.home")}
					className="mb-1 flex size-7 items-center justify-center"
				>
					<img src="/joyjoy-icon.svg" alt={t("nav.home")} className="size-7" />
				</Link>
				<DndContext
					sensors={sensors}
					collisionDetection={closestCenter}
					onDragEnd={onDragEnd}
				>
					<SortableContext
						items={tabs.map((t) => t.key)}
						strategy={verticalListSortingStrategy}
					>
						<div className="flex flex-col items-center gap-1">
							{tabs.map((tab) => (
								<SortableRailTab key={tab.key} tab={tab} />
							))}
						</div>
					</SortableContext>
				</DndContext>
				<div className="flex-1" />
				<button
					type="button"
					onClick={toggleWorkspace}
					title={t("nav.workspace")}
					aria-pressed={workspaceOpen}
					className={cn(
						"group relative flex size-9 items-center justify-center rounded-lg transition-colors",
						workspaceOpen
							? "bg-primary/10 text-primary"
							: "text-muted-foreground hover:bg-foreground/5 hover:text-foreground",
					)}
				>
					{workspaceOpen && <ActiveBar />}
					<FolderTree className="size-5" strokeWidth={1.5} />
				</button>
				<NavLink to="/settings" title={t("nav.settings")} className={railLink}>
					{({ isActive }) => (
						<>
							{isActive && <ActiveBar />}
							<Settings className="size-5" strokeWidth={1.5} />
						</>
					)}
				</NavLink>
			</nav>
			<main className="flex min-w-0 flex-1 flex-col">
				<Outlet />
			</main>
			<WorkspaceDock />
		</div>
	);
}
