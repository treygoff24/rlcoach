"use client";

import { motion, useMotionTemplate, useMotionValue } from "framer-motion";
import { MouseEvent } from "react";

interface HoloCardProps {
	children: React.ReactNode;
	className?: string;
	delay?: number;
}

export function HoloCard({
	children,
	className = "",
	delay = 0,
}: HoloCardProps) {
	const mouseX = useMotionValue(0);
	const mouseY = useMotionValue(0);

	function handleMouseMove({ currentTarget, clientX, clientY }: MouseEvent) {
		const { left, top, width, height } = currentTarget.getBoundingClientRect();

		// Calculate normalized position (0-1)
		const x = (clientX - left) / width;
		const y = (clientY - top) / height;

		// Set motion values for the glow effect
		mouseX.set(clientX - left);
		mouseY.set(clientY - top);
	}

	return (
		<motion.div
			initial={{ opacity: 0, y: 20 }}
			animate={{ opacity: 1, y: 0 }}
			transition={{ duration: 0.5, delay: delay * 0.1 }}
			className={`
        group relative rounded-xl border border-white/10 bg-gray-900/50 
        backdrop-blur-md overflow-hidden
        ${className}
      `}
			onMouseMove={handleMouseMove}
		>
			<motion.div
				className="pointer-events-none absolute -inset-px rounded-xl opacity-0 transition duration-300 group-hover:opacity-100"
				style={{
					background: useMotionTemplate`
            radial-gradient(
              650px circle at ${mouseX}px ${mouseY}px,
              rgba(14, 165, 233, 0.15),
              transparent 80%
            )
          `,
				}}
			/>

			{/* Scanline texture */}
			<div
				className="absolute inset-0 pointer-events-none opacity-[0.03]"
				style={{
					backgroundImage:
						"linear-gradient(to bottom, transparent 50%, #000 50%)",
					backgroundSize: "100% 4px",
				}}
			/>

			<div className="relative h-full">{children}</div>
		</motion.div>
	);
}
