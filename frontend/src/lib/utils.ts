import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}

// A namespaced unique id, e.g. prefixedId("t") -> "t-<uuid>". Single source for
// the thread-id / message-id generators that were duplicated across store + runtime.
export const prefixedId = (prefix: string): string =>
	`${prefix}-${crypto.randomUUID()}`;
