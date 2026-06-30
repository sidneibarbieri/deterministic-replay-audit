export interface PortfolioSummary {
  total_market_value: number;
  total_cost_basis: number;
  total_gain_loss: number;
  total_gain_loss_pct: number;
  position_count: number;
  currency: string;
}

export interface Position {
  ticker: string;
  name: string;
  shares: number;
  current_price: number;
  change_pct?: number | null;
  market_value: number;
  gain_loss: number;
  gain_loss_pct: number;
  weight_pct?: number;
}

export interface PortfolioResponse {
  summary: PortfolioSummary;
  positions: Position[];
  price_source?: string;
  analysis?: {
    source?: string;
    largest_position?: string | null;
  };
  last_updated: string;
}

export interface PortfolioSource {
  active_path: string;
  active_type: 'manual' | 'inbox' | 'private' | 'fixture';
  modified_at: string | null;
  position_count: number;
  manual_override: boolean;
  inbox_path: string;
  latest_broker_export: string | null;
}

export interface RecommendationOrder {
  ticker: string;
  amount: number;
  shares: number;
  fee: number;
}

export interface RankedPosition {
  ticker: string;
  theme: string;
  weight_pct: number;
  moat_class: string;
  compounding_class: string;
  composite_score: number;
  valuation_points: number;
  forward_pe: number | null;
}

export interface RecommendationResponse {
  cash: number;
  provider_mode: string;
  generated_at: string;
  minimum_order_amount: number;
  orders: RecommendationOrder[];
  excluded_overweight: string[];
  excluded_theme: string[];
  ranked_positions: RankedPosition[];
}

export interface DecisionLogEntry {
  id: number;
  created_at: string;
  policy_version: string;
  portfolio_source: string;
  provider_mode: string;
  cash: number;
  order_count: number;
  total_order_amount: number;
}

export interface Candidate {
  ticker: string;
  name: string;
  theme: string;
  live_price: number;
  moat_class: string;
  compounding_class: string;
  composite_score: number;
  valuation_points: number;
  forward_pe: number | null;
  roic: number | null;
}

export interface ReviewAddition {
  ticker: string;
  name: string;
  theme: string;
  composite_score: number;
  portfolio_fit_score: number;
  current_theme_weight_pct: number;
  projected_theme_weight_pct: number;
  structural_role: string;
  reason: string;
}

export interface ReviewReplacement {
  current_ticker: string;
  candidate_ticker: string;
  candidate_name: string;
  score_gap: number;
  reason: string;
}

export interface ReviewTrim {
  ticker: string;
  weight_pct: number;
  composite_score: number;
  reason: string;
}

export interface PortfolioReview {
  current_positions: number;
  target_min_positions: number;
  target_max_positions: number;
  additions_needed: number;
  add_candidates: ReviewAddition[];
  replacement_watch: ReviewReplacement[];
  trim_watch: ReviewTrim[];
}

export interface CandidatesResponse {
  provider_mode: string;
  generated_at: string;
  review: PortfolioReview;
  candidates: Candidate[];
}

export interface ProviderStatus {
  provider_id: string;
  display_name: string;
  env_var: string | null;
  configured: boolean;
  required_for: string;
  free_tier: boolean;
}

export interface ManualTradeRequest {
  action: 'buy' | 'sell';
  ticker: string;
  name?: string;
  shares: number;
  price: number;
  fees: number;
}

async function parseJsonResponse<ResponsePayload>(
  response: Response,
  resourceName: string,
): Promise<ResponsePayload> {
  if (!response.ok) {
    throw new Error(`${resourceName} request failed: ${response.status}`);
  }
  return (await response.json()) as ResponsePayload;
}

export async function fetchPortfolio(
  live: boolean,
  signal: AbortSignal,
): Promise<PortfolioResponse> {
  const parameters = new URLSearchParams({ live: String(live) });
  const response = await fetch(`/api/v1/portfolio/user?${parameters}`, { signal });
  return parseJsonResponse<PortfolioResponse>(response, 'Portfolio');
}

export async function fetchRecommendation(
  cash: number,
  offlineDemo: boolean,
  signal: AbortSignal,
): Promise<RecommendationResponse> {
  const parameters = new URLSearchParams({
    cash: cash.toFixed(2),
    offline_demo: String(offlineDemo),
  });
  const response = await fetch(`/api/v1/portfolio/user/recommendation?${parameters}`, {
    signal,
  });
  return parseJsonResponse<RecommendationResponse>(response, 'Recommendation');
}

export async function fetchCandidates(
  offlineDemo: boolean,
  limit: number,
  signal: AbortSignal,
): Promise<CandidatesResponse> {
  const parameters = new URLSearchParams({
    offline_demo: String(offlineDemo),
    limit: String(limit),
  });
  const response = await fetch(`/api/v1/portfolio/user/candidates?${parameters}`, { signal });
  return parseJsonResponse<CandidatesResponse>(response, 'Candidates');
}

export async function fetchProviderStatus(signal: AbortSignal): Promise<ProviderStatus[]> {
  const response = await fetch('/api/v1/providers/status', { signal });
  return parseJsonResponse<ProviderStatus[]>(response, 'Provider status');
}

export async function recordManualTrade(request: ManualTradeRequest): Promise<PortfolioResponse> {
  const response = await fetch('/api/v1/portfolio/user/trades', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return parseJsonResponse<PortfolioResponse>(response, 'Manual trade');
}

export async function uploadPortfolioCsv(file: File): Promise<PortfolioResponse> {
  const body = new FormData();
  body.append('file', file);
  const response = await fetch('/api/v1/portfolio/user/source/upload', {
    method: 'POST',
    body,
  });
  if (!response.ok) {
    // Surface the backend's parse error so the user can fix their CSV.
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `Upload failed: ${response.status}`);
  }
  return (await response.json()) as PortfolioResponse;
}

export async function fetchPortfolioSource(signal: AbortSignal): Promise<PortfolioSource> {
  const response = await fetch('/api/v1/portfolio/user/source', { signal });
  return parseJsonResponse<PortfolioSource>(response, 'Portfolio source');
}

export async function clearManualPortfolio(): Promise<PortfolioResponse> {
  const response = await fetch('/api/v1/portfolio/user/source/manual', { method: 'DELETE' });
  return parseJsonResponse<PortfolioResponse>(response, 'Manual portfolio reset');
}

export async function fetchDecisionLogs(signal: AbortSignal): Promise<DecisionLogEntry[]> {
  const response = await fetch('/api/v1/portfolio/user/decisions?limit=8', { signal });
  return parseJsonResponse<DecisionLogEntry[]>(response, 'Decision log');
}

export interface AuditReportOverall {
  run_sets: number;
  mean_valid_rate: number;
  mean_policy_jaccard: number;
  mean_stability: number;
  violation_counts: Record<string, number>;
}

export interface AdvisorSummary {
  scenarios: number;
  mean_valid_rate: number;
  mean_policy_jaccard: number;
  mean_stability: number;
  violation_counts: Record<string, number>;
}

export interface AuditResultsResponse {
  version: string;
  description: string;
  scenario_count: number;
  advisor_count: number;
  overall: AuditReportOverall;
  by_advisor: Record<string, AdvisorSummary>;
}

export async function fetchAuditResults(signal: AbortSignal): Promise<AuditResultsResponse> {
  const response = await fetch('/api/v1/portfolio/audit-results', { signal });
  return parseJsonResponse<AuditResultsResponse>(response, 'Audit results');
}
