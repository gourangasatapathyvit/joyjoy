import type {
	AttachmentAdapter,
	CompleteAttachment,
	PendingAttachment,
} from "@assistant-ui/react";
import { workspaceApi } from "@/api/workspace";
import { prefixedId } from "@/lib/utils";

const attType = (mime: string): "image" | "document" | "file" =>
	mime.startsWith("image/")
		? "image"
		: mime === "application/pdf"
			? "document"
			: "file";

// Built-in assistant-ui AttachmentAdapter, wired to the deepagent's filesystem.
// On send it UPLOADS the file into the active thread's workspace (the same store the
// agent + dock use), then yields a text part telling the agent the file is there so
// it reads it with its OWN tools (read_file, or pdftotext/python in the sandbox).
// Model-agnostic: no multimodal/message-block plumbing — an attachment is just a
// workspace file. `getThreadId` reads the live active thread at send time.
export function workspaceAttachmentAdapter(
	getThreadId: () => string,
): AttachmentAdapter {
	return {
		// assistant-ui's fileMatchesAccept treats ONLY the literal "*" as match-all
		// ("*/*" falls through and rejects every file). "*" → accept any file type.
		accept: "*",
		async add({ file }): Promise<PendingAttachment> {
			return {
				id: prefixedId("att"),
				type: attType(file.type),
				name: file.name,
				contentType: file.type || "application/octet-stream",
				file,
				status: { type: "requires-action", reason: "composer-send" },
			};
		},
		async send(attachment): Promise<CompleteAttachment> {
			// Upload into the workspace ROOT of the current thread (dir = "").
			await workspaceApi.upload(getThreadId(), "", attachment.file);
			return {
				id: attachment.id,
				type: attachment.type,
				name: attachment.name,
				contentType: attachment.contentType,
				status: { type: "complete" },
				// State a NEUTRAL fact only — the file exists in the workspace. Do NOT
				// prescribe what to do or how to read it: the agent decides from the
				// user's own message + its tools/skills/MCPs (it already knows its
				// toolchain + working dir from the system prompt).
				content: [
					{
						type: "text",
						text: `[Attached file available in your workspace: ${attachment.name}]`,
					},
				],
			};
		},
		async remove(): Promise<void> {
			// The file lives in the workspace (visible in the dock); nothing to undo here.
		},
	};
}
