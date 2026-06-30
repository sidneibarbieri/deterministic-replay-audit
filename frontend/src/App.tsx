import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  CircleDollarSign,
  FileText,
  RefreshCw,
  Search,
  ShieldCheck,
  WalletCards,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import {
  fetchCandidates,
  fetchDecisionLogs,
  fetchPortfolio,
  fetchPortfolioSource,
  fetchRecommendation,
  recordManualTrade,
  clearManualPortfolio,
  uploadPortfolioCsv,
  type Candidate,
  type CandidatesResponse,
  type DecisionLogEntry,
  type ManualTradeRequest,
  type PortfolioReview,
  type PortfolioResponse,
  type PortfolioSource,
  type Position,
  type RecommendationOrder,
  type RecommendationResponse,
} from './api';
import { DataSourcesHealth } from './components/DataSourcesHealth';
import { PortfolioEditor } from './components/PortfolioEditor';
import { formatDateTime, formatMoney, formatNumber, formatPercent } from './format';
import { type TableSort, useTableSort } from './useTableSort';

const DEFAULT_CASH = 1500.0;

function readInitialCash(): number {
  const cashParameter = new URLSearchParams(window.location.search).get('cash');
  if (!cashParameter) {
    return DEFAULT_CASH;
  }
  return parseCashInput(cashParameter);
}

function readInitialOfflineDemo(): boolean {
  return new URLSearchParams(window.location.search).get('offline_demo') === 'true';
}

function parseCashInput(value: string): number {
  const normalizedValue = value.replace(',', '.').trim();
  const parsedValue = Number(normalizedValue);
  if (!Number.isFinite(parsedValue) || parsedValue <= 0) {
    throw new Error('Cash must be a positive number.');
  }
  return parsedValue;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

function App() {
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const [recommendation, setRecommendation] = useState<RecommendationResponse | null>(null);
  const [candidates, setCandidates] = useState<CandidatesResponse | null>(null);
  const [portfolioSource, setPortfolioSource] = useState<PortfolioSource | null>(null);
  const [decisionLogs, setDecisionLogs] = useState<DecisionLogEntry[]>([]);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);
  const [recommendationError, setRecommendationError] = useState<string | null>(null);
  const [candidateError, setCandidateError] = useState<string | null>(null);
  const [tradeMessage, setTradeMessage] = useState<string | null>(null);
  const [isPortfolioLoading, setIsPortfolioLoading] = useState(true);
  const [isRecommendationLoading, setIsRecommendationLoading] = useState(false);
  const [isCandidateLoading, setIsCandidateLoading] = useState(false);
  const [cashInput, setCashInput] = useState(() => readInitialCash().toFixed(2));
  const [offlineDemo, setOfflineDemo] = useState(() => readInitialOfflineDemo());
  const [refreshIndex, setRefreshIndex] = useState(0);
  const [tradeForm, setTradeForm] = useState<ManualTradeRequest>({
    action: 'buy',
    ticker: '',
    name: '',
    shares: 0,
    price: 0,
    fees: 0,
  });

  useEffect(() => {
    const controller = new AbortController();

    async function loadPortfolio() {
      setIsPortfolioLoading(true);
      setPortfolioError(null);
      // The portfolio valuation stays deterministic so its value does not jump when
      // the reviewer-mode toggle changes. The toggle governs recommendations only.
      const payload = await fetchPortfolio(false, controller.signal);
      setPortfolio(payload);
      setIsPortfolioLoading(false);
    }

    loadPortfolio().catch((error: unknown) => {
      if (isAbortError(error)) {
        return;
      }
      setPortfolioError(error instanceof Error ? error.message : 'Unknown portfolio error');
      setIsPortfolioLoading(false);
    });

    return () => controller.abort();
  }, [refreshIndex]);

  useEffect(() => {
    const controller = new AbortController();

    async function loadPortfolioSource() {
      const payload = await fetchPortfolioSource(controller.signal);
      setPortfolioSource(payload);
    }

    loadPortfolioSource().catch((error: unknown) => {
      if (isAbortError(error)) {
        return;
      }
      setPortfolioError(error instanceof Error ? error.message : 'Unknown portfolio source error');
    });

    return () => controller.abort();
  }, [refreshIndex, portfolio?.analysis?.source]);

  useEffect(() => {
    const controller = new AbortController();

    async function loadDecisionLogs() {
      const payload = await fetchDecisionLogs(controller.signal);
      setDecisionLogs(payload);
    }

    loadDecisionLogs().catch((error: unknown) => {
      if (isAbortError(error)) {
        return;
      }
      setPortfolioError(error instanceof Error ? error.message : 'Unknown decision log error');
    });

    return () => controller.abort();
  }, [refreshIndex]);

  useEffect(() => {
    setCandidates(null);
    setCandidateError(null);
    setRecommendation(null);
    setRecommendationError(null);
  }, [offlineDemo]);

  const positions = useMemo(() => {
    if (!portfolio) {
      return [];
    }
    const denominator = portfolio.summary.total_market_value || 1;
    return portfolio.positions
      .map((position) => ({
        ...position,
        weight_pct: position.weight_pct ?? (position.market_value / denominator) * 100,
      }))
      .sort((firstPosition, secondPosition) => {
        return secondPosition.market_value - firstPosition.market_value;
      });
  }, [portfolio]);

  const largestPosition = positions[0];
  const recommendedCapital =
    recommendation?.orders.reduce((total, order) => total + order.amount, 0) ?? 0;
  const topRanked = recommendation?.ranked_positions[0];

  const rankedRows = useMemo(
    () =>
      (recommendation?.ranked_positions ?? []).map((position, index) => ({
        ...position,
        rank: index + 1,
      })),
    [recommendation],
  );
  const rankingSort = useTableSort(rankedRows, 'composite_score', 'desc');
  const positionSort = useTableSort(positions, 'market_value', 'desc');
  const candidateRows = useMemo(
    () =>
      (candidates?.candidates ?? []).map((candidate, index) => ({
        ...candidate,
        rank: index + 1,
      })),
    [candidates],
  );
  const candidateSort = useTableSort(candidateRows, 'composite_score', 'desc');

  function refreshWorkspace() {
    setRefreshIndex((currentIndex) => currentIndex + 1);
  }

  async function analyzeCashDeployment(): Promise<void> {
    const parsedCash = parseCashInput(cashInput);
    const controller = new AbortController();
    setIsRecommendationLoading(true);
    setRecommendationError(null);
    try {
      const payload = await fetchRecommendation(parsedCash, offlineDemo, controller.signal);
      setRecommendation(payload);
      setRefreshIndex((currentIndex) => currentIndex + 1);
    } catch (error: unknown) {
      setRecommendationError(
        error instanceof Error ? error.message : 'Unknown recommendation error',
      );
    } finally {
      setIsRecommendationLoading(false);
    }
  }

  async function screenUniverse(): Promise<void> {
    const controller = new AbortController();
    setIsCandidateLoading(true);
    setCandidateError(null);
    try {
      const payload = await fetchCandidates(offlineDemo, 12, controller.signal);
      setCandidates(payload);
    } catch (error: unknown) {
      setCandidateError(error instanceof Error ? error.message : 'Unknown candidate error');
    } finally {
      setIsCandidateLoading(false);
    }
  }

  async function submitManualTrade(): Promise<void> {
    setTradeMessage(null);
    setPortfolioError(null);
    try {
      const payload = await recordManualTrade({
        ...tradeForm,
        ticker: tradeForm.ticker.trim().toUpperCase(),
        name: tradeForm.name?.trim() || undefined,
      });
      setPortfolio(payload);
      const ticker = tradeForm.ticker.trim().toUpperCase();
      setTradeMessage(
        `${tradeForm.action === 'buy' ? 'Buy' : 'Sell'} of ${ticker} recorded. Portfolio updated.`,
      );
      setRefreshIndex((currentIndex) => currentIndex + 1);
      setRecommendation(null);
      setTradeForm({
        action: tradeForm.action,
        ticker: '',
        name: '',
        shares: 0,
        price: 0,
        fees: 0,
      });
    } catch (error: unknown) {
      setPortfolioError(error instanceof Error ? error.message : 'Unknown trade error');
    }
  }

  async function resetManualPortfolio(): Promise<void> {
    setTradeMessage(null);
    setPortfolioError(null);
    try {
      const payload = await clearManualPortfolio();
      setPortfolio(payload);
      setTradeMessage('Manual portfolio cleared. Using latest broker export.');
      setRefreshIndex((currentIndex) => currentIndex + 1);
      setRecommendation(null);
    } catch (error: unknown) {
      setPortfolioError(error instanceof Error ? error.message : 'Unknown source reset error');
    }
  }

  async function uploadBrokerCsv(file: File): Promise<void> {
    setTradeMessage(null);
    setPortfolioError(null);
    try {
      const payload = await uploadPortfolioCsv(file);
      setPortfolio(payload);
      setTradeMessage(`Imported ${payload.positions.length} positions from ${file.name}.`);
      setRefreshIndex((currentIndex) => currentIndex + 1);
      setRecommendation(null);
    } catch (error: unknown) {
      setPortfolioError(error instanceof Error ? error.message : 'Unknown upload error');
    }
  }

  return (
    <main className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>
      <aside className="side-rail" aria-label="Workspace navigation">
        <div className="brand-lockup">
          <img className="brand-mark" src="/favicon.svg" alt="" aria-hidden="true" />
          <div>
            <p className="eyebrow">ActionAudit</p>
            <p className="brand-subtitle">Research desk</p>
          </div>
        </div>
        <nav className="rail-nav">
          <a href="#deployment">
            <CircleDollarSign size={17} />
            Deploy cash
          </a>
          <a href="#rankings">
            <BarChart3 size={17} />
            Quality rank
          </a>
          <a href="#candidates">
            <Search size={17} />
            Candidates
          </a>
          <a href="#positions">
            <WalletCards size={17} />
            Positions
          </a>
        </nav>
        <div className="rail-note">
          <ShieldCheck size={17} />
          <span>Read-only portfolio. Orders are proposed, not placed.</span>
        </div>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Moat and compounding workbench</p>
            <h1>ActionAudit</h1>
          </div>
          <button className="icon-button" type="button" onClick={refreshWorkspace}>
            <RefreshCw size={17} />
            Refresh
          </button>
        </header>

        {portfolioError && <StatusBlock tone="danger" message={portfolioError} />}
        {recommendationError && <StatusBlock tone="warning" message={recommendationError} />}
        {candidateError && <StatusBlock tone="warning" message={candidateError} />}

        {portfolio && (
          <>
            <section className="metric-strip" aria-label="Portfolio summary">
              <Metric
                label="Portfolio value"
                value={formatMoney(portfolio.summary.total_market_value)}
              />
              <Metric
                label="Unrealized P/L"
                value={`${formatMoney(portfolio.summary.total_gain_loss)} (${formatPercent(
                  portfolio.summary.total_gain_loss_pct,
                )})`}
                tone={portfolio.summary.total_gain_loss >= 0 ? 'positive' : 'negative'}
              />
              <Metric
                label="Largest position"
                value={largestPosition ? largestPosition.ticker : 'n/a'}
                detail={largestPosition ? formatPercent(largestPosition.weight_pct ?? 0) : undefined}
              />
              <Metric label="Positions" value={String(portfolio.summary.position_count)} />
            </section>

            <ReviewerEvidencePanel
              portfolio={portfolio}
              source={portfolioSource}
              decisionCount={decisionLogs.length}
              offlineDemo={offlineDemo}
              hasRecommendation={recommendation !== null}
            />

            <section className="deployment-band" id="deployment">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Cash deployment</p>
                  <h2>Allocation queue</h2>
                </div>
                <span className="freshness">
                  Data snapshot {formatDateTime(portfolio.last_updated)}
                  {portfolio.analysis?.source ? ` · ${portfolio.analysis.source}` : ''}
                </span>
              </div>

              <div className="control-row">
                <label className="field">
                  <span>Available cash</span>
                  <input
                    inputMode="decimal"
                    type="text"
                    value={cashInput}
                    onChange={(event) => setCashInput(event.target.value)}
                  />
                </label>
                <label className="toggle-field">
                  <input
                    type="checkbox"
                    checked={offlineDemo}
                    onChange={(event) => setOfflineDemo(event.target.checked)}
                  />
                  <span>Deterministic reviewer mode</span>
                </label>
                <button
                  className="primary-button"
                  type="button"
                  onClick={() => {
                    void analyzeCashDeployment();
                  }}
                  disabled={isRecommendationLoading}
                >
                  <Activity size={17} />
                  {isRecommendationLoading ? 'Analyzing...' : 'Analyze'}
                </button>
              </div>

              <p className="mode-hint">
                The portfolio valuation stays fixed. Live mode drives real recommendations;
                reviewer mode swaps in synthetic, reproducible fundamentals for offline demos,
                so only the recommended picks differ and are not actionable.
              </p>

              {isRecommendationLoading && <div className="loading-row">Running analysis...</div>}
              {!recommendation && !isRecommendationLoading && (
                <div className="loading-row">
                  Enter cash and run analysis when you need a deployment plan.
                </div>
              )}
              {recommendation && recommendation.orders.length === 0 && !isRecommendationLoading && (
                <div className="status-block warning">
                  <AlertTriangle size={18} />
                  <span>
                    Cash is below the economic order minimum of{' '}
                    {formatMoney(recommendation.minimum_order_amount)}. Keep it as cash or add more
                    before placing an order.
                  </span>
                </div>
              )}

              {recommendation && recommendation.orders.length > 0 && !isRecommendationLoading && (
                <div className="deployment-layout">
                  <div className="order-stack">
                    <div className="provider-line">
                      <CheckCircle2 size={17} />
                      <span>
                        {recommendation.provider_mode === 'offline-demo'
                          ? 'Reviewer demo (synthetic)'
                          : 'Live data'}{' '}
                        · {formatMoney(recommendedCapital)} queued
                      </span>
                    </div>
                    {recommendation.orders.map((order) => (
                      <OrderRow key={order.ticker} order={order} />
                    ))}
                  </div>

                  <div className="decision-notes">
                    <h3>Guardrails</h3>
                    <p>
                      Overweight:{' '}
                      <strong>{recommendation.excluded_overweight.join(', ') || 'none'}</strong>
                    </p>
                    <p>
                      Theme cap: <strong>{recommendation.excluded_theme.join(', ') || 'none'}</strong>
                    </p>
                    <p>
                      Top rank: <strong>{topRanked?.ticker ?? 'n/a'}</strong>
                      {topRanked ? ` at ${formatNumber(topRanked.composite_score)} points` : ''}
                    </p>
                  </div>
                </div>
              )}
            </section>

            <DataSourcesHealth />

            {portfolioSource && (
              <PortfolioSourcePanel
                source={portfolioSource}
                onResetManual={() => {
                  void resetManualPortfolio();
                }}
                onUpload={(file) => {
                  void uploadBrokerCsv(file);
                }}
              />
            )}

            <DecisionLogPanel decisions={decisionLogs} />

            <PortfolioEditor
              form={tradeForm}
              message={tradeMessage}
              positions={portfolio?.positions ?? []}
              onChange={setTradeForm}
              onSubmit={() => {
                void submitManualTrade();
              }}
            />

            {recommendation && (
              <section className="data-section" id="rankings">
                <div className="section-heading">
                  <div>
                    <p className="eyebrow">Research ranking</p>
                    <h2>Moat, compounding, valuation</h2>
                  </div>
                </div>
                <div className="table-frame">
                  <table>
                    <thead>
                      <tr>
                        <SortHeader label="#" columnKey="rank" sort={rankingSort} numeric />
                        <SortHeader label="Ticker" columnKey="ticker" sort={rankingSort} />
                        <SortHeader label="Theme" columnKey="theme" sort={rankingSort} />
                        <SortHeader
                          label="Weight"
                          columnKey="weight_pct"
                          sort={rankingSort}
                          numeric
                        />
                        <SortHeader label="Moat" columnKey="moat_class" sort={rankingSort} />
                        <SortHeader
                          label="Compounding"
                          columnKey="compounding_class"
                          sort={rankingSort}
                        />
                        <SortHeader
                          label="Score"
                          columnKey="composite_score"
                          sort={rankingSort}
                          numeric
                        />
                        <SortHeader
                          label="Valuation"
                          columnKey="valuation_points"
                          sort={rankingSort}
                          numeric
                        />
                        <SortHeader label="fPE" columnKey="forward_pe" sort={rankingSort} numeric />
                      </tr>
                    </thead>
                    <tbody>
                      {rankingSort.sortedRows.map((rankedPosition) => (
                        <tr key={rankedPosition.ticker}>
                          <td className="numeric">{rankedPosition.rank}</td>
                          <td className="ticker-cell">{rankedPosition.ticker}</td>
                          <td>{rankedPosition.theme}</td>
                          <td className="numeric">{formatPercent(rankedPosition.weight_pct)}</td>
                          <td>{rankedPosition.moat_class}</td>
                          <td>{rankedPosition.compounding_class}</td>
                          <td className="numeric">
                            {formatNumber(rankedPosition.composite_score)}
                          </td>
                          <td className="numeric">
                            {formatNumber(rankedPosition.valuation_points)}
                          </td>
                          <td className="numeric">
                            {rankedPosition.forward_pe
                              ? formatNumber(rankedPosition.forward_pe)
                              : 'n/a'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            <section className="data-section" id="candidates">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">External universe</p>
                  <h2>Candidate screen</h2>
                </div>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => {
                    void screenUniverse();
                  }}
                  disabled={isCandidateLoading}
                >
                  <Search size={17} />
                  {isCandidateLoading ? 'Screening...' : 'Screen universe'}
                </button>
              </div>
              <p className="mode-hint">
                Screens a curated list of high-quality stocks, ADRs, and REITs not currently held.
                Use live mode for market data; reviewer mode is synthetic and reproducible.
              </p>

              {candidates && (
                <div className="candidate-meta">
                  <CheckCircle2 size={17} />
                  <span>
                    {candidates.provider_mode === 'offline-demo'
                      ? 'Reviewer demo (synthetic)'
                      : 'Live data'}{' '}
                    · {candidateRows.length} candidates · screened{' '}
                    {formatDateTime(candidates.generated_at)}
                  </span>
                </div>
              )}

              {candidates && <PortfolioReviewPanel review={candidates.review} />}

              {candidates && (
                <div className="table-frame">
                  <table>
                    <thead>
                      <tr>
                        <SortHeader label="#" columnKey="rank" sort={candidateSort} numeric />
                        <SortHeader label="Ticker" columnKey="ticker" sort={candidateSort} />
                        <SortHeader label="Theme" columnKey="theme" sort={candidateSort} />
                        <SortHeader
                          label="Price"
                          columnKey="live_price"
                          sort={candidateSort}
                          numeric
                        />
                        <SortHeader label="Moat" columnKey="moat_class" sort={candidateSort} />
                        <SortHeader
                          label="Compounding"
                          columnKey="compounding_class"
                          sort={candidateSort}
                        />
                        <SortHeader
                          label="Score"
                          columnKey="composite_score"
                          sort={candidateSort}
                          numeric
                        />
                        <SortHeader
                          label="Valuation"
                          columnKey="valuation_points"
                          sort={candidateSort}
                          numeric
                        />
                        <SortHeader label="ROIC" columnKey="roic" sort={candidateSort} numeric />
                        <SortHeader label="fPE" columnKey="forward_pe" sort={candidateSort} numeric />
                      </tr>
                    </thead>
                    <tbody>
                      {candidateSort.sortedRows.map((candidate) => (
                        <CandidateRow key={candidate.ticker} candidate={candidate} />
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="data-section" id="positions">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Current holdings</p>
                  <h2>Portfolio positions</h2>
                </div>
                <span className={`price-badge ${portfolio.price_source === 'live' ? 'live' : ''}`}>
                  {portfolio.price_source === 'live' ? 'Live prices' : 'Stored prices'}
                </span>
              </div>
              {positions.length === 0 ? (
                <div className="loading-row">
                  No positions found. Import a broker CSV or add a manual trade.
                </div>
              ) : (
                <div className="table-frame">
                  <table>
                    <thead>
                      <tr>
                        <SortHeader label="Ticker" columnKey="ticker" sort={positionSort} />
                        <SortHeader label="Name" columnKey="name" sort={positionSort} />
                        <SortHeader label="Shares" columnKey="shares" sort={positionSort} numeric />
                        <SortHeader
                          label="Price"
                          columnKey="current_price"
                          sort={positionSort}
                          numeric
                        />
                        <SortHeader label="Day" columnKey="change_pct" sort={positionSort} numeric />
                        <SortHeader
                          label="Value"
                          columnKey="market_value"
                          sort={positionSort}
                          numeric
                        />
                        <SortHeader
                          label="Weight"
                          columnKey="weight_pct"
                          sort={positionSort}
                          numeric
                        />
                        <SortHeader label="P/L" columnKey="gain_loss" sort={positionSort} numeric />
                      </tr>
                    </thead>
                    <tbody>
                      {positionSort.sortedRows.map((position) => (
                        <PositionRow key={position.ticker} position={position} />
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        )}

        {isPortfolioLoading && (
          <div className="loading-row" id="main-content">Loading portfolio...</div>
        )}
      </section>
    </main>
  );
}

interface MetricProps {
  label: string;
  value: string;
  detail?: string;
  tone?: 'positive' | 'negative';
}

function Metric({ label, value, detail, tone }: MetricProps) {
  const toneClass = tone ? `metric-value ${tone}` : 'metric-value';
  return (
    <div className="metric">
      <span>{label}</span>
      <strong className={toneClass}>{value}</strong>
      {detail && <small>{detail}</small>}
    </div>
  );
}

interface StatusBlockProps {
  tone: 'warning' | 'danger';
  message: string;
}

function StatusBlock({ tone, message }: StatusBlockProps) {
  return (
    <div className={`status-block ${tone}`}>
      <AlertTriangle size={18} />
      <span>{message}</span>
    </div>
  );
}

interface ReviewerEvidencePanelProps {
  portfolio: PortfolioResponse;
  source: PortfolioSource | null;
  decisionCount: number;
  offlineDemo: boolean;
  hasRecommendation: boolean;
}

function ReviewerEvidencePanel({
  portfolio,
  source,
  decisionCount,
  offlineDemo,
  hasRecommendation,
}: ReviewerEvidencePanelProps) {
  const activeSource = source
    ? `${source.active_type} · ${source.position_count} positions`
    : 'source loading';
  const dataMode = offlineDemo ? 'Reviewer demo' : 'Live data';
  const decisionState = hasRecommendation ? 'decision recorded' : 'waiting for analysis';
  return (
    <section className="evidence-panel" aria-label="Reviewer evidence">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Reviewer evidence</p>
          <h2>Reproducibility, source, audit trail</h2>
        </div>
        <span className="freshness">Orders are proposed, not placed</span>
      </div>
      <div className="evidence-grid">
        <EvidenceCard
          label="Reproduce"
          value="make verify"
          detail="Runs lint, tests, frontend build, and ESLint."
          code="make all"
        />
        <EvidenceCard
          label="Active source"
          value={activeSource}
          detail={
            source?.modified_at
              ? `Modified ${formatDateTime(source.modified_at)}`
              : 'Waiting for source metadata.'
          }
          code={source?.manual_override ? 'manual override' : 'immutable input'}
        />
        <EvidenceCard
          label="Decision mode"
          value={dataMode}
          detail={
            offlineDemo
              ? 'Synthetic replay mode for offline review.'
              : `Portfolio refreshed ${formatDateTime(portfolio.last_updated)}.`
          }
          code={decisionState}
        />
        <EvidenceCard
          label="Audit trail"
          value={`${decisionCount} recent runs`}
          detail="Every recommendation stores policy, source, mode, cash, and queued orders."
          code="deterministic policy"
        />
      </div>
    </section>
  );
}

interface EvidenceCardProps {
  label: string;
  value: string;
  detail: string;
  code: string;
}

function EvidenceCard({ label, value, detail, code }: EvidenceCardProps) {
  return (
    <div className="evidence-card">
      <span className="review-label">{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
      <code>{code}</code>
    </div>
  );
}

interface PortfolioSourcePanelProps {
  source: PortfolioSource;
  onResetManual: () => void;
  onUpload: (file: File) => void;
}

function PortfolioSourcePanel({ source, onResetManual, onUpload }: PortfolioSourcePanelProps) {
  return (
    <section className="provider-panel" aria-label="Portfolio source">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Portfolio source</p>
          <h2>Import status</h2>
        </div>
        <div className="source-actions">
          <label className="secondary-button file-button">
            Upload broker CSV
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) {
                  onUpload(file);
                }
                event.target.value = '';
              }}
            />
          </label>
          {source.manual_override && (
            <button className="secondary-button" type="button" onClick={onResetManual}>
              Use broker export
            </button>
          )}
        </div>
      </div>
      <div className="provider-list">
        <div className="provider-row">
          <div className="provider-name">
            <FileText size={17} />
            <strong>{source.active_type}</strong>
          </div>
          <span>{source.active_path}</span>
          <code>{source.position_count} positions</code>
        </div>
        <div className="provider-row">
          <div className="provider-name">
            <RefreshCw size={17} />
            <strong>Modified</strong>
          </div>
          <span>{source.modified_at ? formatDateTime(source.modified_at) : 'unknown'}</span>
          <code>{source.manual_override ? 'manual override' : 'broker source'}</code>
        </div>
        <div className="provider-row">
          <div className="provider-name">
            <WalletCards size={17} />
            <strong>Inbox</strong>
          </div>
          <span>{source.inbox_path}</span>
          <code>{source.latest_broker_export ?? 'no broker export'}</code>
        </div>
      </div>
      <p className="mode-hint">
        Upload a broker CSV export to update the portfolio. Manual edits
        become the active source until cleared.
      </p>
    </section>
  );
}

function DecisionLogPanel({ decisions }: { decisions: DecisionLogEntry[] }) {
  return (
    <section className="provider-panel" aria-label="Decision log">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Audit trail</p>
          <h2>Decision log</h2>
        </div>
        <span className="freshness">{decisions.length} recent runs</span>
      </div>
      {decisions.length === 0 ? (
        <div className="loading-row">No recommendation runs recorded yet.</div>
      ) : (
        <div className="table-frame">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Policy</th>
                <th>Source</th>
                <th>Mode</th>
                <th className="numeric">Cash</th>
                <th className="numeric">Orders</th>
                <th className="numeric">Queued</th>
              </tr>
            </thead>
            <tbody>
              {decisions.map((decision) => (
                <tr key={decision.id}>
                  <td>{formatDateTime(decision.created_at)}</td>
                  <td>{decision.policy_version}</td>
                  <td>{decision.portfolio_source}</td>
                  <td>{decision.provider_mode}</td>
                  <td className="numeric">{formatMoney(decision.cash)}</td>
                  <td className="numeric">{decision.order_count}</td>
                  <td className="numeric">{formatMoney(decision.total_order_amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mode-hint">
        Each recommendation run is recorded with policy, source, provider mode, cash, and queued
        order totals.
      </p>
    </section>
  );
}

interface OrderRowProps {
  order: RecommendationOrder;
}

function OrderRow({ order }: OrderRowProps) {
  return (
    <article className="order-row">
      <div>
        <span>Buy</span>
        <strong>{order.ticker}</strong>
      </div>
      <div className="order-meta">
        <span>{formatMoney(order.amount)}</span>
        <span>{formatNumber(order.shares)} shares</span>
        <span>{formatMoney(order.fee)} fee</span>
      </div>
    </article>
  );
}

interface PortfolioReviewPanelProps {
  review: PortfolioReview;
}

function PortfolioReviewPanel({ review }: PortfolioReviewPanelProps) {
  const targetRange = `${review.target_min_positions}-${review.target_max_positions}`;
  return (
    <div className="review-grid" aria-label="Deterministic portfolio review">
      <div className="review-column">
        <span className="review-label">Portfolio size</span>
        <strong>
          {review.current_positions} holdings · target {targetRange}
        </strong>
        <small>
          {review.additions_needed > 0
            ? `${review.additions_needed} addition needed to reach the range.`
            : 'Within the target range.'}
        </small>
      </div>
      <div className="review-column">
        <span className="review-label">Addition watch</span>
        <ReviewList
          emptyLabel="No external candidate cleared the current screen."
          items={review.add_candidates.map((candidate) => ({
            key: candidate.ticker,
            label: `${candidate.ticker} · ${candidate.structural_role}`,
            detail: `${formatNumber(candidate.portfolio_fit_score)} fit · ${candidate.theme} ${formatPercent(candidate.current_theme_weight_pct)} -> ${formatPercent(candidate.projected_theme_weight_pct)}`,
          }))}
        />
      </div>
      <div className="review-column">
        <span className="review-label">Upgrade watch</span>
        <ReviewList
          emptyLabel="No deterministic replacement signal."
          items={review.replacement_watch.map((replacement) => ({
            key: `${replacement.current_ticker}-${replacement.candidate_ticker}`,
            label: `${replacement.current_ticker} -> ${replacement.candidate_ticker}`,
            detail: `+${formatNumber(replacement.score_gap)} score gap`,
          }))}
        />
      </div>
      <div className="review-column">
        <span className="review-label">Trim watch</span>
        <ReviewList
          emptyLabel="No overweight lower-score position."
          items={review.trim_watch.map((trim) => ({
            key: trim.ticker,
            label: `${trim.ticker} · ${formatPercent(trim.weight_pct)}`,
            detail: `${formatNumber(trim.composite_score)} pts`,
          }))}
        />
      </div>
    </div>
  );
}

interface ReviewListItem {
  key: string;
  label: string;
  detail: string;
}

interface ReviewListProps {
  emptyLabel: string;
  items: ReviewListItem[];
}

function ReviewList({ emptyLabel, items }: ReviewListProps) {
  if (items.length === 0) {
    return <small>{emptyLabel}</small>;
  }
  return (
    <ul className="review-list">
      {items.slice(0, 3).map((item) => (
        <li key={item.key}>
          <strong>{item.label}</strong>
          <span>{item.detail}</span>
        </li>
      ))}
    </ul>
  );
}

interface CandidateRowProps {
  candidate: Candidate & { rank: number };
}

function CandidateRow({ candidate }: CandidateRowProps) {
  return (
    <tr>
      <td className="numeric">{candidate.rank}</td>
      <td className="ticker-cell">{candidate.ticker}</td>
      <td>{candidate.theme}</td>
      <td className="numeric">{formatMoney(candidate.live_price)}</td>
      <td>{candidate.moat_class}</td>
      <td>{candidate.compounding_class}</td>
      <td className="numeric">{formatNumber(candidate.composite_score)}</td>
      <td className="numeric">{formatNumber(candidate.valuation_points)}</td>
      <td className="numeric">{candidate.roic === null ? 'n/a' : formatPercent(candidate.roic)}</td>
      <td className="numeric">
        {candidate.forward_pe === null ? 'n/a' : formatNumber(candidate.forward_pe)}
      </td>
    </tr>
  );
}

interface PositionRowProps {
  position: Position;
}

function PositionRow({ position }: PositionRowProps) {
  const weight = position.weight_pct ?? 0;
  const gainClass = position.gain_loss >= 0 ? 'positive' : 'negative';
  const dayChange = position.change_pct ?? null;
  let dayClass = '';
  if (dayChange !== null) {
    dayClass = dayChange >= 0 ? 'positive' : 'negative';
  }
  return (
    <tr>
      <td className="ticker-cell">{position.ticker}</td>
      <td>{position.name}</td>
      <td className="numeric">{formatNumber(position.shares)}</td>
      <td className="numeric">{formatMoney(position.current_price)}</td>
      <td className={`numeric ${dayClass}`}>
        {dayChange === null ? '-' : formatPercent(dayChange)}
      </td>
      <td className="numeric">{formatMoney(position.market_value)}</td>
      <td className="numeric">{formatPercent(weight)}</td>
      <td className={`numeric ${gainClass}`}>
        {formatMoney(position.gain_loss)} ({formatPercent(position.gain_loss_pct)})
      </td>
    </tr>
  );
}

interface SortHeaderProps<Row> {
  label: string;
  columnKey: keyof Row;
  sort: TableSort<Row>;
  numeric?: boolean;
}

function SortHeader<Row>({ label, columnKey, sort, numeric = false }: SortHeaderProps<Row>) {
  const isActive = sort.sortKey === columnKey;
  let indicator = '';
  if (isActive) {
    indicator = sort.sortDirection === 'asc' ? ' ▲' : ' ▼';
  }
  return (
    <th className={numeric ? 'numeric' : undefined}>
      <button type="button" className="th-sort" onClick={() => sort.toggleSort(columnKey)}>
        {label}
        {indicator}
      </button>
    </th>
  );
}

export default App;
