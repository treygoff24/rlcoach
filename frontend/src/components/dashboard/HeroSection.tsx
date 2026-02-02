"use client";

import { motion } from "framer-motion";
import { HoloCard } from "./HoloCard";

interface HeroSectionProps {
	totalReplays: number;
	rankName?: string;
	rankTier?: number;
}

export function HeroSection({
	totalReplays,
	rankName = "Unranked",
	rankTier = 0,
}: HeroSectionProps) {
	return (
		<div className="relative w-full mb-8">
			<div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
				{/* Main Identity Card */}
				<div className="lg:col-span-2">
					<HoloCard className="p-8 flex items-center justify-between min-h-[200px]">
						<div className="z-10 relative">
							<motion.div
								initial={{ opacity: 0, x: -20 }}
								animate={{ opacity: 1, x: 0 }}
								transition={{ delay: 0.2 }}
							>
								<h2 className="text-white/50 text-sm font-mono tracking-widest uppercase mb-2">
									Command Center // Pilot
								</h2>
								<h1 className="text-5xl md:text-6xl font-display text-white tracking-wide uppercase drop-shadow-[0_0_15px_rgba(255,255,255,0.3)]">
									{rankName}
								</h1>
								<div className="flex items-center gap-4 mt-4">
									<div className="px-3 py-1 bg-white/5 border border-white/10 rounded text-xs text-white/70 font-mono">
										TIER {rankTier}
									</div>
									<div className="px-3 py-1 bg-boost/10 border border-boost/20 rounded text-xs text-boost font-mono flex items-center gap-2">
										<span className="w-2 h-2 rounded-full bg-boost animate-pulse" />
										ONLINE
									</div>
								</div>
							</motion.div>
						</div>

						{/* Decorative Rank Icon / Graphic Placeholder */}
						<div className="absolute right-0 top-0 bottom-0 w-1/2 opacity-20 pointer-events-none">
							<div className="w-full h-full bg-gradient-radial from-white/20 to-transparent transform scale-150 translate-x-1/4" />
						</div>
					</HoloCard>
				</div>

				{/* Secondary Stats Card */}
				<div className="lg:col-span-1">
					<HoloCard
						className="p-6 flex flex-col justify-center h-full"
						delay={2}
					>
						<h3 className="text-white/50 text-xs font-mono mb-4 uppercase tracking-widest">
							Database Status
						</h3>
						<div className="flex items-baseline gap-2">
							<span className="text-4xl font-display text-white">
								{totalReplays}
							</span>
							<span className="text-sm text-white/50">replays analyzed</span>
						</div>

						{/* Progress bar visual */}
						<div className="w-full h-1 bg-white/10 mt-6 rounded-full overflow-hidden">
							<motion.div
								initial={{ width: 0 }}
								animate={{ width: "100%" }}
								transition={{ duration: 1.5, ease: "circOut" }}
								className="h-full bg-gradient-to-r from-boost via-white to-boost"
							/>
						</div>
						<div className="flex justify-between mt-2 text-[10px] text-white/30 font-mono">
							<span>SYNC: ACTIVE</span>
							<span>100%</span>
						</div>
					</HoloCard>
				</div>
			</div>
		</div>
	);
}
