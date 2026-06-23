import { DownloadIcon, ExternalLinkIcon, FileIcon } from "lucide-react";
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

interface ImagePart {
	image: string;
	filename?: string;
}
interface FilePart {
	data: string;
	mimeType?: string;
	filename?: string;
}

// Inline image with click-to-open. If the source 404s (e.g. an imported
// conversation referencing a file that isn't on this machine) it renders nothing
// rather than a broken-image chip, keeping imported transcripts clean.
export function MediaImage({ image, filename }: ImagePart) {
	const [failed, setFailed] = useState(false);
	const name = filename ? baseName(filename) : "image";
	if (failed) return null;
	return (
		<figure className="my-2">
			<a href={image} target="_blank" rel="noreferrer" title={name}>
				<img
					src={image}
					alt={name}
					onError={() => setFailed(true)}
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

// Open + Download chip for files we don't render inline (or that failed to load).
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
// iframe. Falls back to a download chip if conversion/serving fails.
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

	if (failed) return <FileChip data={data} name={name} />;
	if (!src)
		return (
			<p className="my-2 text-xs text-muted-foreground">Converting {name}…</p>
		);
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
// everything else as a monospace block). Renders nothing if the fetch fails.
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

	if (failed) return null;
	if (text == null)
		return (
			<p className="my-2 text-xs text-muted-foreground">Loading {name}…</p>
		);
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
		return (
			<figure className="my-2">
				<iframe
					src={data}
					title={name}
					className="h-96 w-full rounded-lg border border-border"
				/>
				<figcaption className="mt-1 text-[11px] text-muted-foreground">
					{name}
				</figcaption>
			</figure>
		);

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
		return (
			<audio src={data} controls className="my-2 w-full max-w-md">
				{name}
			</audio>
		);

	if (mime.startsWith("video/") || isVideoFile(name))
		return (
			<video
				src={data}
				controls
				className="my-2 max-h-96 max-w-full rounded-lg"
			>
				{name}
			</video>
		);

	if (isMarkdownFile(name))
		return <TextFileView data={data} name={name} markdown />;

	if (isTextFile(name) || mime.startsWith("text/"))
		return <TextFileView data={data} name={name} markdown={false} />;

	return <FileChip data={data} name={name} />;
}
