import { AlertCircle, CheckCircle2, CircleDashed, RefreshCw } from 'lucide-react';
import { useEffect, useState } from 'react';

interface DataSourceHealth {
  provider_id: string;
  name: string;
  status: 'configured' | 'working' | 'not_configured' | 'error';
  configured: boolean;
  last_check: string;
  error: string | null;
  metadata: Record<string, string | number | boolean>;
}

interface DataSourcesHealthResponse {
  timestamp: string;
  live: boolean;
  sources: DataSourceHealth[];
  summary: {
    total: number;
    working: number;
    configured: number;
    not_configured: number;
    errors: number;
  };
}

export function DataSourcesHealth() {
  const [health, setHealth] = useState<DataSourcesHealthResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLiveChecking, setIsLiveChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function fetchHealth(live: boolean): Promise<void> {
    const parameters = new URLSearchParams({ live: String(live) });
    const response = await fetch(`/api/v1/data-sources/health?${parameters}`);
    if (!response.ok) {
      throw new Error(`Data source health failed: ${response.status}`);
    }
    setHealth((await response.json()) as DataSourcesHealthResponse);
    setError(null);
  }

  useEffect(() => {
    fetchHealth(false)
      .catch((requestError: unknown) => {
        setError(requestError instanceof Error ? requestError.message : 'Unknown health error');
      })
      .finally(() => setIsLoading(false));
  }, []);

  async function runLiveCheck(): Promise<void> {
    setIsLiveChecking(true);
    try {
      await fetchHealth(true);
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : 'Unknown health error');
    } finally {
      setIsLiveChecking(false);
    }
  }

  return (
    <section className="provider-panel" aria-label="Data sources health">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Data sources</p>
          <h2>Health status</h2>
          <p className="heading-note">
            Configuration is checked on load. Live checks are explicit to avoid slow startup and
            rate-limit noise.
          </p>
        </div>
        <button
          className="secondary-button"
          type="button"
          onClick={() => {
            void runLiveCheck();
          }}
          disabled={isLiveChecking}
        >
          <RefreshCw size={17} />
          {isLiveChecking ? 'Checking...' : 'Run live check'}
        </button>
      </div>

      {isLoading && <div className="loading-row">Loading data source readiness...</div>}
      {error && <StatusLine message={error} />}
      {health && <HealthSummary health={health} />}
    </section>
  );
}

function HealthSummary({ health }: { health: DataSourcesHealthResponse }) {
  return (
    <>
      <div className="review-grid">
        <HealthMetric label="Total" value={health.summary.total} />
        <HealthMetric
          label={health.live ? 'Working' : 'Ready'}
          value={health.live ? health.summary.working : health.summary.configured}
          tone="positive"
        />
        <HealthMetric label="Configured" value={health.summary.configured} />
        <HealthMetric
          label="Errors"
          value={health.summary.errors}
          tone={health.summary.errors > 0 ? 'negative' : 'positive'}
        />
      </div>

      <div className="provider-list">
        {health.sources.map((source) => (
          <div className="provider-row" key={source.provider_id}>
            <div className="provider-name">
              <SourceIcon status={source.status} />
              <strong>{source.name}</strong>
            </div>
            <span>{source.metadata.purpose}</span>
            <code className={`source-status status-pill ${source.status}`}>
              {source.error ?? source.status.replace('_', ' ')}
            </code>
          </div>
        ))}
      </div>

      <p className="mode-hint">
        {health.live ? 'Live check' : 'Configuration check'} · Last updated{' '}
        {new Date(health.timestamp).toLocaleString()}
      </p>
    </>
  );
}

function SourceIcon({ status }: { status: DataSourceHealth['status'] }) {
  if (status === 'working') {
    return <CheckCircle2 className="source-icon working" size={17} />;
  }
  if (status === 'error') {
    return <AlertCircle className="source-icon error" size={17} />;
  }
  return <CircleDashed className={`source-icon ${status}`} size={17} />;
}

function HealthMetric({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: 'positive' | 'negative';
}) {
  return (
    <div className="review-column">
      <span className="review-label">{label}</span>
      <strong className={tone}>{value}</strong>
    </div>
  );
}

function StatusLine({ message }: { message: string }) {
  return (
    <div className="status-block danger">
      <AlertCircle size={18} />
      <span>{message}</span>
    </div>
  );
}
