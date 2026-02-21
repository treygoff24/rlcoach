// frontend/src/app/(dashboard)/page.tsx
"use client";

import { useState, useEffect } from "react";
import { useSession } from "next-auth/react";
import { HeroSection } from "@/components/dashboard/HeroSection";
import { StatGrid } from "@/components/dashboard/StatGrid";
import { HoloCard } from "@/components/dashboard/HoloCard";
import { BoostGauge } from "@/components/dashboard/BoostGauge";
import { MechanicsEqualizer } from "@/components/dashboard/MechanicsEqualizer";
import { TelemetryFeed } from "@/components/dashboard/TelemetryFeed";

interface MechanicStat {
	name: string;
	count: number;
}

interface DashboardStats {
	total_replays: number;
	recent_win_rate: number | null;
	avg_goals: number | null;
	avg_assists: number | null;
	avg_saves: number | null;
	avg_shots: number | null;
	top_mechanics: MechanicStat[];
	recent_trend: "up" | "down" | "stable";
	has_data: boolean;
}

interface BenchmarkData {
	rank_tier: number;
	rank_name: string;
	comparisons: Record<string, any>;
	has_data: boolean;
}

export default function DashboardHome() {
	const { data: session } = useSession();
	const [stats, setStats] = useState<DashboardStats | null>(null);
	const [benchmarks, setBenchmarks] = useState<BenchmarkData | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		async function fetchData() {
			if (!session?.accessToken) {
				setLoading(false);
				return;
			}

			try {
				const [statsRes, benchmarksRes] = await Promise.all([
					fetch("/api/v1/users/me/dashboard", {
						headers: {
							Authorization: `Bearer ${session.accessToken}`,
						},
					}),
					fetch("/api/v1/users/me/benchmarks", {
						headers: {
							Authorization: `Bearer ${session.accessToken}`,
						},
					}),
				]);

				if (!statsRes.ok) {
					if (statsRes.status === 401) {
						setError("Session expired. Please sign in again.");
					} else {
						setError("Failed to load dashboard stats.");
					}
					return;
				}

				const statsData = await statsRes.json();
				setStats(statsData);

				if (benchmarksRes.ok) {
					const benchmarksData = await benchmarksRes.json();
					setBenchmarks(benchmarksData);
				}
			} catch {
				setError("Unable to connect to server.");
			} finally {
				setLoading(false);
			}
		}

		fetchData();
	}, [session?.accessToken]);

	if (loading) {
		return (
			<div className="flex items-center justify-center min-h-[60vh]">
				<div className="flex flex-col items-center gap-4">
					<div className="w-16 h-16 border-4 border-boost/30 border-t-boost rounded-full animate-spin" />
					<p className="text-boost/60 font-mono animate-pulse">
						INITIALIZING CONTROL ROOM...
					</p>
				</div>
			</div>
		);
	}

	if (error) {
		return (
			<div className="flex items-center justify-center min-h-[60vh]">
				<HoloCard className="p-8 max-w-md text-center">
					<h2 className="text-fire font-display text-2xl mb-2">SYSTEM ERROR</h2>
					<p className="text-white/60 mb-6">{error}</p>
					<button
						type="button"
						onClick={() => window.location.reload()}
						className="px-6 py-2 bg-white/10 hover:bg-white/20 rounded border border-white/10 transition-colors"
					>
						RETRY CONNECTION
					</button>
				</HoloCard>
			</div>
		);
	}

	// Placeholder empty state or "no data" state logic can go here,
	// but for now let's render the dashboard with whatever we have or 0s.
	const safeStats = stats || {
		total_replays: 0,
		recent_win_rate: 0,
		avg_goals: 0,
		avg_assists: 0,
		avg_saves: 0,
		avg_shots: 0,
		top_mechanics: [],
		recent_trend: "stable",
		has_data: false,
	};

	const shootingPct =
		safeStats.avg_shots && safeStats.avg_goals
			? (safeStats.avg_goals / safeStats.avg_shots) * 100
			: 0;

	return (
		<div className="p-4 md:p-8 space-y-6 max-w-[1600px] mx-auto">
			{/* Top Row: Hero & Telemetry */}
			<div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
				<div className="lg:col-span-2">
					<HeroSection
						totalReplays={safeStats.total_replays}
						rankName={benchmarks?.rank_name || "UNRANKED"}
						rankTier={benchmarks?.rank_tier || 0}
					/>
				</div>
				<div className="lg:col-span-1 h-full min-h-[250px]">
					<HoloCard className="h-full">
						<TelemetryFeed />
					</HoloCard>
				</div>
			</div>

			{/* Middle Row: Stats Grid */}
			<StatGrid>
				<HoloCard className="p-4" delay={3}>
					<div className="text-white/40 text-xs font-mono mb-2 uppercase">
						Avg Goals
					</div>
					<div className="text-4xl font-display text-white">
						{safeStats.avg_goals?.toFixed(1) || "0.0"}
					</div>
				</HoloCard>
				<HoloCard className="p-4" delay={3.5}>
					<div className="text-white/40 text-xs font-mono mb-2 uppercase">
						Avg Assists
					</div>
					<div className="text-4xl font-display text-white">
						{safeStats.avg_assists?.toFixed(1) || "0.0"}
					</div>
				</HoloCard>
				<HoloCard className="p-4" delay={4}>
					<div className="text-white/40 text-xs font-mono mb-2 uppercase">
						Avg Saves
					</div>
					<div className="text-4xl font-display text-white">
						{safeStats.avg_saves?.toFixed(1) || "0.0"}
					</div>
				</HoloCard>
				<HoloCard className="p-4" delay={4.5}>
					<div className="text-white/40 text-xs font-mono mb-2 uppercase">
						Shooting %
					</div>
					<div className="text-4xl font-display text-white">
						{shootingPct.toFixed(1)}%
					</div>
					<div className="mt-2 w-full bg-white/10 h-1 rounded-full overflow-hidden">
						<div
							className="h-full bg-plasma"
							style={{ width: `${shootingPct}%` }}
						/>
					</div>
				</HoloCard>
			</StatGrid>

			{/* Bottom Row: Mechanics & Win Rate */}
			<div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
				<div className="lg:col-span-2">
					<HoloCard className="h-full min-h-[300px]" delay={5}>
						<div className="absolute top-4 left-4 z-10">
							<h3 className="font-display text-lg text-white/80">
								MECHANICS FREQUENCY
							</h3>
						</div>
						<div className="pt-12 h-full">
							<MechanicsEqualizer mechanics={safeStats.top_mechanics} />
						</div>
					</HoloCard>
				</div>
				<div className="lg:col-span-1">
					<HoloCard
						className="h-full min-h-[300px] flex items-center justify-center bg-gradient-to-br from-black/40 to-boost/5"
						delay={6}
					>
						<BoostGauge
							value={safeStats.recent_win_rate || 0}
							label="Win Rate"
							sublabel="Last 20 Games"
							color={
								(safeStats.recent_win_rate || 0) >= 60
									? "boost"
									: (safeStats.recent_win_rate || 0) >= 50
										? "plasma"
										: "fire"
							}
						/>
					</HoloCard>
				</div>
			</div>
		</div>
	);
}
