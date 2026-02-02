"use client";

import { motion } from "framer-motion";

interface BoostGaugeProps {
	value: number; // 0-100
	label: string;
	sublabel?: string;
	color?: "boost" | "fire" | "plasma";
	delay?: number;
}

export function BoostGauge({
	value,
	label,
	sublabel,
	color = "boost",
	delay = 0,
}: BoostGaugeProps) {
	const radius = 40;
	const circumference = 2 * Math.PI * radius;
	const progress = Math.min(Math.max(value, 0), 100);
	const strokeDashoffset = circumference - (progress / 100) * circumference;

	const colors = {
		boost: "text-boost",
		fire: "text-fire",
		plasma: "text-plasma",
	};

	const strokeColors = {
		boost: "#00D4FF",
		fire: "#FF6B35",
		plasma: "#8B5CF6",
	};

	return (
		<div className="flex flex-col items-center justify-center p-4">
			<div className="relative w-32 h-32 flex items-center justify-center">
				{/* Creating a glow effect behind the gauge */}
				<div
					className={`absolute inset-0 rounded-full blur-xl opacity-20 bg-current ${colors[color]}`}
				/>

				<svg
					className="w-full h-full -rotate-90 transform"
					viewBox="0 0 100 100"
				>
					{/* Background circle */}
					<circle
						cx="50"
						cy="50"
						r={radius}
						fill="transparent"
						stroke="currentColor"
						strokeWidth="8"
						className="text-white/10"
					/>
					{/* Progress circle */}
					<motion.circle
						initial={{ strokeDashoffset: circumference }}
						animate={{ strokeDashoffset }}
						transition={{ duration: 1.5, ease: "easeOut", delay: delay * 0.1 }}
						cx="50"
						cy="50"
						r={radius}
						fill="transparent"
						stroke={strokeColors[color]} // Using hex for stroke to work with motion
						strokeWidth="8"
						strokeDasharray={circumference}
						strokeLinecap="round"
						className="drop-shadow-[0_0_10px_rgba(0,0,0,0.5)]"
					/>
				</svg>

				{/* Value text in center */}
				<div className="absolute inset-0 flex flex-col items-center justify-center">
					<motion.span
						initial={{ opacity: 0, scale: 0.5 }}
						animate={{ opacity: 1, scale: 1 }}
						transition={{ delay: delay * 0.1 + 0.5 }}
						className="text-2xl font-bold font-display text-white tracking-wider"
					>
						{value.toFixed(0)}
					</motion.span>
				</div>
			</div>

			<div className="mt-2 text-center">
				<p className="text-white font-medium tracking-wide uppercase text-sm">
					{label}
				</p>
				{sublabel && <p className="text-white/40 text-xs">{sublabel}</p>}
			</div>
		</div>
	);
}
