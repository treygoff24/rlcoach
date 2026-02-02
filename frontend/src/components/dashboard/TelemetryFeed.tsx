"use client";

import { motion } from "framer-motion";

const MOCK_LOGS = [
	{ id: 1, type: "info", msg: "System initialized. Waiting for input." },
	{ id: 2, type: "success", msg: "Connection to local backend established." },
	{ id: 3, type: "warning", msg: "Boost efficiency below optimal levels." },
	{ id: 4, type: "info", msg: "Analysing replay: 2v2_stadium_final.replay" },
];

export function TelemetryFeed() {
	return (
		<div className="font-mono text-xs p-4 h-full overflow-hidden flex flex-col justify-end">
			<div className="text-white/30 mb-2 border-b border-white/10 pb-1 uppercase tracking-widest text-[10px]">
				System Log
			</div>
			<div className="space-y-1">
				{MOCK_LOGS.map((log, i) => (
					<motion.div
						key={log.id}
						initial={{ opacity: 0, x: -10 }}
						animate={{ opacity: 1, x: 0 }}
						transition={{ delay: 1 + i * 0.1 }}
						className="flex items-center gap-2"
					>
						<span className="text-white/20">
							[{new Date().toLocaleTimeString()}]
						</span>
						<span
							className={`
                        ${log.type === "success" ? "text-victory" : ""}
                        ${log.type === "warning" ? "text-fire" : ""}
                        ${log.type === "info" ? "text-boost" : ""}
                    `}
						>
							{">"}
						</span>
						<span className="text-white/60">{log.msg}</span>
					</motion.div>
				))}
				<motion.div
					animate={{ opacity: [0, 1, 0] }}
					transition={{ duration: 1, repeat: Infinity }}
					className="w-2 h-4 bg-boost/50 mt-1"
				/>
			</div>
		</div>
	);
}
