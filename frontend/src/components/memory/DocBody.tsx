import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Textarea } from "@/components/ui/textarea";

// Renders the document body: a raw textarea in edit mode, otherwise a
// formatted markdown view (.md) or a plain text block.
export function DocBody({
	editing,
	name,
	draft,
	onChange,
	loading,
}: {
	editing: boolean;
	name: string;
	draft: string;
	onChange: (v: string) => void;
	loading?: boolean;
}) {
	const { t } = useTranslation();
	if (loading)
		return (
			<p className="text-sm text-muted-foreground">{t("common.loading")}</p>
		);
	if (editing)
		return (
			<Textarea
				value={draft}
				onChange={(e) => onChange(e.target.value)}
				className="min-h-0 flex-1 resize-none font-mono text-xs"
				placeholder={t("memory.emptyPlaceholder")}
			/>
		);
	if (name.toLowerCase().endsWith(".md"))
		return (
			<div className="min-h-0 flex-1 overflow-y-auto">
				<div className="markdown-body mx-auto w-full max-w-3xl">
					<ReactMarkdown remarkPlugins={[remarkGfm]}>
						{draft || `_${t("memory.emptyPlaceholder")}_`}
					</ReactMarkdown>
				</div>
			</div>
		);
	return (
		<pre className="min-h-0 flex-1 overflow-auto rounded-md bg-muted/40 p-3 font-mono text-xs text-foreground">
			{draft}
		</pre>
	);
}
