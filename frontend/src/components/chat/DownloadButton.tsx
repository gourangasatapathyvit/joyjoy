import type { ReactNode } from "react";
import { DotMatrix } from "@/components/assistant-ui/dot-matrix";
import { useFileDownload } from "@/lib/useFileDownload";

// Download trigger that streams the file (via useFileDownload) and swaps its icon
// for the dot-matrix "downloading" pattern while in flight. Replaces a plain
// <a download> so the transfer has a visible state.
export function DownloadButton({
	url,
	filename,
	title,
	className,
	children,
}: {
	url: string;
	filename: string;
	title?: string;
	className?: string;
	children: ReactNode;
}) {
	const { downloading, download } = useFileDownload();
	return (
		<button
			type="button"
			title={title}
			aria-busy={downloading}
			onClick={(e) => {
				e.stopPropagation();
				if (!downloading) download(url, filename);
			}}
			className={className}
		>
			{downloading ? (
				<DotMatrix state="downloading" className="size-3.5" label={title} />
			) : (
				children
			)}
		</button>
	);
}
