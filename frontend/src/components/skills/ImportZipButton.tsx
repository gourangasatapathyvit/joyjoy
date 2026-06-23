import { Upload } from "lucide-react";
import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { useSkillMutations } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { fileToBase64 } from "@/lib/text";

// Import a skill folder from a .zip (SKILL.md + helper tree). Used both to create
// a new skill and to re-import/replace an existing one.
export function ImportZipButton({
	defaultName,
	onImported,
	label,
}: {
	defaultName?: string;
	onImported: (name: string) => void;
	label: string;
}) {
	const { t } = useTranslation();
	const { importZip } = useSkillMutations();
	const inputRef = useRef<HTMLInputElement>(null);

	const onPick = async (file: File) => {
		const base = file.name.replace(/\.zip$/i, "");
		const name = (
			defaultName ??
			window.prompt(
				t("skills.importNamePrompt", "Name for the imported skill:"),
				base,
			) ??
			""
		).trim();
		if (!name) return;
		const zip_b64 = await fileToBase64(file);
		importZip.mutate(
			{ name, zip_b64 },
			{
				onSuccess: (r) => {
					if (r?.ok === false) window.alert(r.error ?? "import failed");
					else onImported(name);
				},
			},
		);
	};

	return (
		<>
			<input
				ref={inputRef}
				type="file"
				accept=".zip,application/zip"
				className="hidden"
				onChange={(e) => {
					const f = e.target.files?.[0];
					if (f) onPick(f);
					e.target.value = "";
				}}
			/>
			<Button
				size="sm"
				variant="outline"
				onClick={() => inputRef.current?.click()}
				disabled={importZip.isPending}
			>
				<Upload className="size-3.5" />{" "}
				{importZip.isPending ? t("common.saving") : label}
			</Button>
		</>
	);
}
