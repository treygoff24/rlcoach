"use client";

import { motion } from "framer-motion";

interface Mechanic {
	name: string;
	count: number;
}

interface MechanicsEqualizerProps {
	mechanics: Mechanic[];
	maxCount?: number;
}

export function MechanicsEqualizer({
	mechanics,
	maxCount,
}: MechanicsEqualizerProps) {
	// Determine max value for scaling if not provided
	const max = maxCount || Math.max(...mechanics.map((m) => m.count), 1);

	return (
		<div className="w-full h-full flex items-end justify-between gap-2 p-4 min-h-[200px]">
			{mechanics.map((mech, index) => {
				const heightPercent = (mech.count / max) * 100;

				return (
					<div
						key={mech.name}
						className="flex flex-col items-center justify-end h-full flex-1 gap-2 group"
					>
						{/* Tooltip-ish value */}
						<div className="opacity-0 group-hover:opacity-100 transition-opacity absolute -mt-8 bg-gray-900 text-xs px-2 py-1 rounded border border-white/10 z-10">
							{mech.count}
						</div>

						{/* Bar */}
						<motion.div
							initial={{ height: "0%" }}
							animate={{ height: `${heightPercent}%` }}
							transition={{
								duration: 0.8,
								delay: index * 0.1,
								type: "spring",
								stiffness: 100,
							}}
							className="w-full max-w-[24px] rounded-t-sm bg-gradient-to-t from-plasma/40 via-plasma to-white/80 shadow-[0_0_15px_rgba(139,92,246,0.5)] relative overflow-hidden"
						>
							{/* Internal animation/shine */}
							<motion.div
								animate={{ y: ["100%", "-100%"] }}
								transition={{ repeat: Infinity, duration: 2, ease: "linear" }}
								className="absolute inset-0 bg-white/20 skew-y-12"
							/>
						</motion.div>

						{/* Label */}
						<p className="text-[10px] md:text-xs text-white/60 font-medium truncate w-full text-center rotate-0 md:-rotate-45 md:origin-top-left md:mt-2 md:mb-4">
							{mech.name}
						</p>
					</div>
				);
			})}
		</div>
	);
}
