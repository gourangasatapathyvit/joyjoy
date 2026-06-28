import { useCallback, useState } from "react";

// Streams a file to disk while exposing progress, so callers can show a live
// "downloading" state (and a 0..1 fraction when the server sends Content-Length).
// Falls back to a plain blob download if the body isn't streamable.
export function useFileDownload() {
	const [downloading, setDownloading] = useState(false);
	const [progress, setProgress] = useState<number | null>(null);

	const download = useCallback(async (url: string, filename: string) => {
		setDownloading(true);
		setProgress(null);
		try {
			const res = await fetch(url, { credentials: "include" });
			if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);

			const total = Number(res.headers.get("content-length") || 0);
			let blob: Blob;
			const reader = res.body?.getReader();
			if (reader) {
				const chunks: Uint8Array[] = [];
				let received = 0;
				for (;;) {
					const { done, value } = await reader.read();
					if (done) break;
					if (value) {
						chunks.push(value);
						received += value.length;
						if (total > 0) setProgress(Math.min(1, received / total));
					}
				}
				blob = new Blob(chunks as BlobPart[]);
			} else {
				blob = await res.blob();
			}

			const objectUrl = URL.createObjectURL(blob);
			const a = document.createElement("a");
			a.href = objectUrl;
			a.download = filename;
			document.body.appendChild(a);
			a.click();
			a.remove();
			URL.revokeObjectURL(objectUrl);
		} finally {
			setDownloading(false);
			setProgress(null);
		}
	}, []);

	return { downloading, progress, download };
}
