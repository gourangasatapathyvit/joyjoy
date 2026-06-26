"use client";

import { StreamdownTextPrimitive } from "@assistant-ui/react-streamdown";
import { code } from "@streamdown/code";
import { mermaid } from "@streamdown/mermaid";
import { type FC, memo } from "react";

// Streamdown-based markdown renderer. Replaces the prior
// @assistant-ui/react-markdown renderer (which had no code highlighting):
//   - block-aware streaming with incomplete-markdown repair (remend),
//   - built-in Shiki syntax highlighting via the `code` plugin,
//   - Mermaid diagram rendering via the `mermaid` plugin (```mermaid blocks).
// GFM is on by default in streamdown; its prose styles ship in streamdown's
// styles.css (imported in index.css).
const MarkdownTextImpl: FC = () => {
	return (
		<StreamdownTextPrimitive
			className="aui-md"
			plugins={{ code, mermaid }}
			shikiTheme={["github-light", "github-dark"]}
			defer
		/>
	);
};

export const MarkdownText = memo(MarkdownTextImpl);
