"use client";

import { ReactNode } from "react";

export function StatGrid({ children }: { children: ReactNode }) {
	return (
		<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 auto-rows-min">
			{children}
		</div>
	);
}
