export interface MechanicStat {
	name: string;
	count: number;
}

export interface StatComparison {
	value: number;
	benchmark: number;
	rank_name: string;
	difference: number;
	percentage: number;
	comparison: string;
}

export interface BenchmarkResponse {
	rank_tier: number;
	rank_name: string;
	comparisons: Record<string, StatComparison>;
	has_data: boolean;
}

export interface PaginatedResponse<T> {
	items: T[];
	total: number;
	limit: number;
	offset: number;
}

interface ReplaySummary {
	id: string;
	filename: string;
	status: string;
	played_at: string | null;
	map_name: string | null;
	playlist: string | null;
	team_size: number | null;
	result: string | null;
	my_score: number | null;
	opponent_score: number | null;
}

export interface ReplayListItem extends ReplaySummary {
	replay_id?: string | null;
	created_at: string;
}

export interface ReplayDetail<TPlayer> extends ReplaySummary {
	duration_seconds: number | null;
	overtime: boolean;
	players: TPlayer[];
}
