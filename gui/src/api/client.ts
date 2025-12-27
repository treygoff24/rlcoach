import axios from 'axios';
import type {
  DashboardResponse,
  Game,
  ReplayDetail,
  ReplayFull,
  TrendsResponse,
  Benchmark,
  CompareResponse,
  PatternsResponse,
  WeaknessesResponse,
  Player,
  PlayerDetail,
  PaginatedResponse,
  TagRequest,
} from '../types/api';

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
});

// Dashboard
export async function getDashboard(): Promise<DashboardResponse> {
  const { data } = await api.get<DashboardResponse>('/dashboard');
  return data;
}

// Games
export interface GamesParams {
  playlist?: string;
  result?: 'WIN' | 'LOSS' | 'DRAW';
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
  sort?: string;
}

export async function getGames(params: GamesParams = {}): Promise<PaginatedResponse<Game>> {
  const { data } = await api.get<PaginatedResponse<Game>>('/games', { params });
  return data;
}

export async function getReplay(replayId: string): Promise<ReplayDetail> {
  const { data } = await api.get<ReplayDetail>(`/replays/${encodeURIComponent(replayId)}`);
  return data;
}

export async function getReplayFull(replayId: string): Promise<ReplayFull> {
  const { data } = await api.get<ReplayFull>(`/replays/${encodeURIComponent(replayId)}/full`);
  return data;
}

// Analysis
export interface TrendsParams {
  metric: string;
  period?: string;
  playlist?: string;
}

export async function getTrends(params: TrendsParams): Promise<TrendsResponse> {
  const { data } = await api.get<TrendsResponse>('/trends', { params });
  return data;
}

export interface BenchmarksParams {
  metric?: string;
  playlist?: string;
  rank?: string;
}

export async function getBenchmarks(params: BenchmarksParams = {}): Promise<{ items: Benchmark[] }> {
  const { data } = await api.get<{ items: Benchmark[] }>('/benchmarks', { params });
  return data;
}

export interface CompareParams {
  rank: string;
  playlist?: string;
  period?: string;
}

export async function getComparison(params: CompareParams): Promise<CompareResponse> {
  const { data } = await api.get<CompareResponse>('/compare', { params });
  return data;
}

export interface PatternsParams {
  playlist?: string;
  period?: string;
  min_games?: number;
}

export async function getPatterns(params: PatternsParams = {}): Promise<PatternsResponse> {
  const { data } = await api.get<PatternsResponse>('/patterns', { params });
  return data;
}

export interface WeaknessesParams {
  playlist?: string;
  rank?: string;
  period?: string;
}

export async function getWeaknesses(params: WeaknessesParams = {}): Promise<WeaknessesResponse> {
  const { data } = await api.get<WeaknessesResponse>('/weaknesses', { params });
  return data;
}

// Players
export interface PlayersParams {
  tagged?: boolean;
  min_games?: number;
  limit?: number;
  offset?: number;
  sort?: string;
}

export async function getPlayers(params: PlayersParams = {}): Promise<PaginatedResponse<Player>> {
  const { data } = await api.get<PaginatedResponse<Player>>('/players', { params });
  return data;
}

export async function getPlayer(playerId: string): Promise<PlayerDetail> {
  const { data } = await api.get<PlayerDetail>(`/players/${encodeURIComponent(playerId)}`);
  return data;
}

export async function tagPlayer(playerId: string, request: TagRequest): Promise<Player> {
  const { data } = await api.post<Player>(`/players/${encodeURIComponent(playerId)}/tag`, request);
  return data;
}

// Health check
export async function getHealth(): Promise<{ status: string; version: string; database: string }> {
  const { data } = await api.get('/health');
  return data;
}

export default api;
