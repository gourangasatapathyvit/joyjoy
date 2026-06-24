import {
	DownloadIcon,
	ExternalLinkIcon,
	FileIcon,
	FileWarningIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
	asPdf,
	isAudioFile,
	isImageFile,
	isMarkdownFile,
	isOfficeFile,
	isPdfFile,
	isTextFile,
	isVideoFile,
} from "@/lib/media";
import { baseName } from "@/lib/text";

// Renderers for assistant-ui's native `image` / `file` content parts. The runtime
// (convertMessage) emits these from MEDIA: markers, agent-written workspace files,
// and read_file base64 blocks — so the chat shows the agent's media inline:
// images / gif, audio, video, pdf, OFFICE docs (server-converted to PDF), and
// markdown / code / text files (fetched + rendered).
//
// Every inline renderer first PROBES the source with `fetch` (which, unlike an
// <img>/<audio>/<video>/<iframe> src, does NOT log a console 404 when missing).
// If the source isn't reachable — deleted file, broken path, imported transcript
// referencing a file not on this machine, failed office conversion — it shows a
// single "Media inaccessible" placeholder instead of a broken element.

interface ImagePart {
	image: string;
	filename?: string;
}
interface FilePart {
	data: string;
	mimeType?: string;
	filename?: string;
}

type MediaState = "loading" | "ok" | "error";

// Probe a media URL and, when reachable, expose a blob object-URL to feed the
// element (one fetch, no second network hit, no console 404 on failure). `data:`
// URLs are inline and always available, so they pass straight through.
function useMediaSrc(url: string): { state: MediaState; src: string } {
	const isData = url.startsWith("data:");
	const [state, setState] = useState<MediaState>(isData ? "ok" : "loading");
	const [src, setSrc] = useState<string>(isData ? url : "");

	useEffect(() => {
		if (url.startsWith("data:")) {
			setState("ok");
			setSrc(url);
			return;
		}
		let cancelled = false;
		let obj: string | null = null;
		setState("loading");
		setSrc("");
		fetch(url)
			.then((r) =>
				r.ok ? r.blob() : Promise.reject(new Error(String(r.status))),
			)
			.then((b) => {
				if (cancelled) return;
				obj = URL.createObjectURL(b);
				setSrc(obj);
				setState("ok");
			})
			.catch(() => !cancelled && setState("error"));
		return () => {
			cancelled = true;
			if (obj) URL.revokeObjectURL(obj);
		};
	}, [url]);

	return { state, src };
}

// Shown for any inline media that can't be fetched.
function MediaInaccessible({ name }: { name: string }) {
	return (
		<span className="my-2 inline-flex items-center gap-2 rounded-lg border border-dashed border-border bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
			<FileWarningIcon className="size-4 shrink-0" />
			<span>Media inaccessible</span>
			{name && <span className="truncate text-xs opacity-70">— {name}</span>}
		</span>
	);
}

function MediaLoading({ name }: { name: string }) {
	return <p className="my-2 text-xs text-muted-foreground">Loading {name}…</p>;
}

// Inline image with click-to-open; "Media inaccessible" if the source can't load.
export function MediaImage({ image, filename }: ImagePart) {
	const name = filename ? baseName(filename) : "image";
	const { state, src } = useMediaSrc(image);
	if (state === "error") return <MediaInaccessible name={name} />;
	if (state === "loading") return <MediaLoading name={name} />;
	return (
		<figure className="my-2">
			<a href={image} target="_blank" rel="noreferrer" title={name}>
				<img
					src={src}
					alt={name}
					className="max-h-96 max-w-full rounded-lg border border-border object-contain"
				/>
			</a>
			{filename && (
				<figcaption className="mt-1 text-[11px] text-muted-foreground">
					{name}
				</figcaption>
			)}
		</figure>
	);
}

function PdfView({ data, name }: { data: string; name: string }) {
	const { state, src } = useMediaSrc(data);
	if (state === "error") return <MediaInaccessible name={name} />;
	if (state === "loading") return <MediaLoading name={name} />;
	return (
		<figure className="my-2">
			<iframe
				src={src}
				title={name}
				className="h-96 w-full rounded-lg border border-border"
			/>
			<figcaption className="mt-1 text-[11px] text-muted-foreground">
				{name}
			</figcaption>
		</figure>
	);
}

function AudioView({ data, name }: { data: string; name: string }) {
	const { state, src } = useMediaSrc(data);
	if (state === "error") return <MediaInaccessible name={name} />;
	if (state === "loading") return <MediaLoading name={name} />;
	return <audio src={src} controls className="my-2 w-full max-w-md" />;
}

function VideoView({ data, name }: { data: string; name: string }) {
	const { state, src } = useMediaSrc(data);
	if (state === "error") return <MediaInaccessible name={name} />;
	if (state === "loading") return <MediaLoading name={name} />;
	return (
		<video src={src} controls className="my-2 max-h-96 max-w-full rounded-lg" />
	);
}

// Open + Download chip for files we don't render inline (always-available data
// URLs, or formats with no inline preview).
function FileChip({ data, name }: { data: string; name: string }) {
	return (
		<span className="my-2 inline-flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm">
			<FileIcon className="size-4 text-muted-foreground" />
			<span className="font-medium">{name}</span>
			<a
				href={data}
				target="_blank"
				rel="noreferrer"
				className="ml-1 inline-flex items-center gap-1 text-xs text-primary hover:underline"
			>
				<ExternalLinkIcon className="size-3.5" /> Open
			</a>
			<a
				href={data}
				download={name}
				className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
			>
				<DownloadIcon className="size-3.5" /> Download
			</a>
		</span>
	);
}

// Office docs: fetch the server-converted PDF as a blob and preview it in an
// iframe. Shows "Media inaccessible" if the doc can't be fetched/converted.
function OfficeView({ data, name }: { data: string; name: string }) {
	const [src, setSrc] = useState<string | null>(null);
	const [failed, setFailed] = useState(false);
	useEffect(() => {
		let url: string | null = null;
		let cancelled = false;
		fetch(asPdf(data))
			.then((r) => (r.ok ? r.blob() : Promise.reject(new Error("convert"))))
			.then((b) => {
				if (cancelled) return;
				url = URL.createObjectURL(b);
				setSrc(url);
			})
			.catch(() => !cancelled && setFailed(true));
		return () => {
			cancelled = true;
			if (url) URL.revokeObjectURL(url);
		};
	}, [data]);

	if (failed) return <MediaInaccessible name={name} />;
	if (!src) return <MediaLoading name={name} />;
	return (
		<figure className="my-2">
			<iframe
				src={src}
				title={name}
				className="h-96 w-full rounded-lg border border-border"
			/>
			<figcaption className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
				{name}
				<a href={data} download={name} className="text-primary hover:underline">
					Download
				</a>
			</figcaption>
		</figure>
	);
}

// Markdown / code / text files: fetch the content and render (markdown formatted,
// everything else as a monospace block). "Media inaccessible" if the fetch fails.
function TextFileView({
	data,
	name,
	markdown,
}: {
	data: string;
	name: string;
	markdown: boolean;
}) {
	const [text, setText] = useState<string | null>(null);
	const [failed, setFailed] = useState(false);
	useEffect(() => {
		let cancelled = false;
		fetch(data)
			.then((r) => (r.ok ? r.text() : Promise.reject(new Error("fetch"))))
			.then((tx) => !cancelled && setText(tx))
			.catch(() => !cancelled && setFailed(true));
		return () => {
			cancelled = true;
		};
	}, [data]);

	if (failed) return <MediaInaccessible name={name} />;
	if (text == null) return <MediaLoading name={name} />;
	return (
		<figure className="my-2 overflow-hidden rounded-lg border border-border">
			<figcaption className="border-b border-border bg-muted/40 px-3 py-1.5 text-[11px] text-muted-foreground">
				{name}
			</figcaption>
			{markdown ? (
				<div className="markdown-body max-h-[28rem] overflow-auto p-3">
					<ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
				</div>
			) : (
				<pre className="max-h-[28rem] overflow-auto p-3 font-mono text-xs whitespace-pre-wrap break-words text-foreground">
					{text}
				</pre>
			)}
		</figure>
	);
}

// Route a file part to the right renderer (by extension first, then mime).
export function MediaFile({ data, mimeType, filename }: FilePart) {
	const name = filename ? baseName(filename) : "file";
	const mime = mimeType ?? "";
	const isDataUrl = data.startsWith("data:");

	if (mime.startsWith("image/") || isImageFile(name))
		return <MediaImage image={data} filename={filename} />;

	if (mime === "application/pdf" || isPdfFile(name))
		return <PdfView data={data} name={name} />;

	if (isOfficeFile(name)) {
		// Office → PDF conversion is server-side; a base64 data URL can't be
		// converted on the client, so offer it as a download instead.
		return isDataUrl ? (
			<FileChip data={data} name={name} />
		) : (
			<OfficeView data={data} name={name} />
		);
	}

	if (mime.startsWith("audio/") || isAudioFile(name))
		return <AudioView data={data} name={name} />;

	if (mime.startsWith("video/") || isVideoFile(name))
		return <VideoView data={data} name={name} />;

	if (isMarkdownFile(name))
		return <TextFileView data={data} name={name} markdown />;

	if (isTextFile(name) || mime.startsWith("text/"))
		return <TextFileView data={data} name={name} markdown={false} />;

	return <FileChip data={data} name={name} />;
}
