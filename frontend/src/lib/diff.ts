// Minimal LCS-based line diff for rendering edit_file / write_file previews.
// Pure + dependency-free so it can be unit-tested in isolation.

export type DiffRow = {
	type: "ctx" | "add" | "del";
	text: string;
	/** 1-based line number in the OLD text (undefined for additions). */
	oldNo?: number;
	/** 1-based line number in the NEW text (undefined for deletions). */
	newNo?: number;
};

/** Split into lines WITHOUT inventing a trailing empty line for "" (so an empty
 * string diffs as zero lines, not one blank line). */
function toLines(text: string): string[] {
	return text === "" ? [] : text.split("\n");
}

/**
 * Compute a line-level diff between `oldText` and `newText`.
 *
 * Returns rows in display order. Common lines are `ctx`, lines only in old are
 * `del`, lines only in new are `add`. Uses the classic LCS DP + backtrack, so a
 * minimal edit script is produced (shared lines are preserved as context rather
 * than shown as delete+add churn).
 *
 * Edge cases: oldText="" → all additions; newText="" → all deletions; identical
 * → all context; both "" → [].
 */
export function computeLineDiff(oldText: string, newText: string): DiffRow[] {
	const a = toLines(oldText);
	const b = toLines(newText);
	const n = a.length;
	const m = b.length;

	// dp[i][j] = LCS length of a[i:] and b[j:].
	const dp: number[][] = Array.from({ length: n + 1 }, () =>
		new Array<number>(m + 1).fill(0),
	);
	for (let i = n - 1; i >= 0; i--) {
		for (let j = m - 1; j >= 0; j--) {
			dp[i][j] =
				a[i] === b[j]
					? dp[i + 1][j + 1] + 1
					: Math.max(dp[i + 1][j], dp[i][j + 1]);
		}
	}

	const rows: DiffRow[] = [];
	let i = 0;
	let j = 0;
	while (i < n && j < m) {
		if (a[i] === b[j]) {
			rows.push({ type: "ctx", text: a[i], oldNo: i + 1, newNo: j + 1 });
			i++;
			j++;
		} else if (dp[i + 1][j] >= dp[i][j + 1]) {
			rows.push({ type: "del", text: a[i], oldNo: i + 1 });
			i++;
		} else {
			rows.push({ type: "add", text: b[j], newNo: j + 1 });
			j++;
		}
	}
	while (i < n) rows.push({ type: "del", text: a[i], oldNo: ++i });
	while (j < m) rows.push({ type: "add", text: b[j], newNo: ++j });
	return rows;
}

/** Convenience counts for a header like "+3 −1". */
export function diffStats(rows: DiffRow[]): { added: number; removed: number } {
	let added = 0;
	let removed = 0;
	for (const r of rows) {
		if (r.type === "add") added++;
		else if (r.type === "del") removed++;
	}
	return { added, removed };
}
