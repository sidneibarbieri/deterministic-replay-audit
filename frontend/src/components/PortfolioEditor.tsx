import { AlertTriangle, CheckCircle2, TrendingDown, TrendingUp } from 'lucide-react';

import type { ManualTradeRequest, Position } from '../api';
import { formatMoney, formatNumber } from '../format';

interface PortfolioEditorProps {
  form: ManualTradeRequest;
  message: string | null;
  positions: Position[];
  onChange: (form: ManualTradeRequest) => void;
  onSubmit: () => void;
}

export function PortfolioEditor({
  form,
  message,
  positions,
  onChange,
  onSubmit,
}: PortfolioEditorProps) {
  const isBuy = form.action === 'buy';
  const ticker = form.ticker.trim().toUpperCase();
  const owned = positions.find((position) => position.ticker.toUpperCase() === ticker) ?? null;
  const sellable = [...positions].sort((a, b) => a.ticker.localeCompare(b.ticker));

  function update<Key extends keyof ManualTradeRequest>(
    key: Key,
    value: ManualTradeRequest[Key],
  ): void {
    onChange({ ...form, [key]: value });
  }

  function setAction(action: 'buy' | 'sell'): void {
    onChange({ ...form, action });
  }

  function selectSellTicker(value: string): void {
    const next = positions.find((position) => position.ticker === value) ?? null;
    onChange({
      ...form,
      ticker: value,
      name: next?.name ?? form.name,
      price: next ? next.current_price : form.price,
    });
  }

  const shares = form.shares || 0;
  const price = form.price || 0;
  const fees = form.fees || 0;
  const gross = shares * price;
  const totalCost = gross + fees;
  const proceeds = gross - fees;
  const remaining = owned ? owned.shares - shares : 0;

  const errors: string[] = [];
  if (!ticker) {
    errors.push('Enter a ticker symbol.');
  }
  if (shares <= 0) {
    errors.push('Shares must be greater than zero.');
  }
  if (price <= 0) {
    errors.push('Price must be greater than zero.');
  }
  if (fees < 0) {
    errors.push('Fees cannot be negative.');
  }
  if (!isBuy && gross > 0 && fees > gross) {
    errors.push('Fees cannot exceed gross proceeds.');
  }
  if (!isBuy && ticker) {
    if (!owned) {
      errors.push(`You do not hold ${ticker}.`);
    } else if (shares > owned.shares) {
      errors.push(`You own only ${formatNumber(owned.shares)} shares of ${ticker}.`);
    }
  }
  const valid = errors.length === 0;

  return (
    <section className="data-section" aria-label="Portfolio editor">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Manual portfolio</p>
          <h2>Buy or sell</h2>
        </div>
      </div>

      <div className="editor-actions" role="group" aria-label="Trade action">
        <button
          type="button"
          className={`editor-action${isBuy ? ' editor-action--buy-active' : ''}`}
          aria-pressed={isBuy}
          onClick={() => setAction('buy')}
        >
          <TrendingUp size={16} />
          Buy
        </button>
        <button
          type="button"
          className={`editor-action${!isBuy ? ' editor-action--sell-active' : ''}`}
          aria-pressed={!isBuy}
          onClick={() => setAction('sell')}
        >
          <TrendingDown size={16} />
          Sell
        </button>
      </div>

      <div className="trade-form">
        <label className="field">
          <span>Ticker</span>
          {isBuy ? (
            <input
              type="text"
              autoComplete="off"
              spellCheck={false}
              placeholder="e.g. MSFT"
              value={form.ticker}
              onChange={(event) => update('ticker', event.target.value)}
            />
          ) : (
            <select value={form.ticker} onChange={(event) => selectSellTicker(event.target.value)}>
              <option value="">Select a holding…</option>
              {sellable.map((position) => (
                <option key={position.ticker} value={position.ticker}>
                  {position.ticker} · {formatNumber(position.shares)} sh
                </option>
              ))}
            </select>
          )}
        </label>

        {isBuy && (
          <label className="field field--wide">
            <span>Name {owned ? '(adding to holding)' : '(new position)'}</span>
            <input
              type="text"
              placeholder={owned ? owned.name : 'Company name'}
              value={form.name ?? ''}
              onChange={(event) => update('name', event.target.value)}
            />
          </label>
        )}

        <label className="field">
          <span>Shares</span>
          <input
            inputMode="decimal"
            type="number"
            min="0"
            step="0.000001"
            value={form.shares || ''}
            onChange={(event) => update('shares', Number(event.target.value))}
          />
        </label>

        <label className="field">
          <span>Price</span>
          <input
            inputMode="decimal"
            type="number"
            min="0"
            step="0.01"
            value={form.price || ''}
            onChange={(event) => update('price', Number(event.target.value))}
          />
        </label>

        <label className="field">
          <span>Transaction fee</span>
          <input
            inputMode="decimal"
            type="number"
            min="0"
            step="0.01"
            placeholder="0.00"
            value={form.fees || ''}
            onChange={(event) => update('fees', Number(event.target.value))}
          />
          <small className="field-hint">Use 0 for fee-free or promotional orders.</small>
        </label>
      </div>

      <div className={`trade-preview${isBuy ? ' trade-preview--buy' : ' trade-preview--sell'}`}>
        {shares > 0 && price > 0 ? (
          <>
            <div className="preview-row">
              <span>{isBuy ? 'Total cost' : 'Net proceeds'}</span>
              <strong>{formatMoney(isBuy ? totalCost : proceeds)}</strong>
            </div>
            <div className="preview-detail">
              {formatNumber(shares)} sh × {formatMoney(price)} {isBuy ? '+' : '−'}{' '}
              {formatMoney(fees)} fees
            </div>
            {!isBuy && owned && shares <= owned.shares && (
              <div className="preview-detail">
                {remaining === 0
                  ? 'Closes the position.'
                  : `Leaves ${formatNumber(remaining)} shares.`}
              </div>
            )}
            {isBuy && owned && (
              <div className="preview-detail">
                Adds to {formatNumber(owned.shares)} shares you own.
              </div>
            )}
          </>
        ) : (
          <div className="preview-empty">
            Enter shares and price to preview {isBuy ? 'cost' : 'proceeds'}.
          </div>
        )}
      </div>

      <div className="editor-footer">
        {!valid && (
          <p className="validation-hint">
            <AlertTriangle size={15} />
            <span>{errors[0]}</span>
          </p>
        )}
        <button
          className="primary-button"
          type="button"
          disabled={!valid}
          onClick={onSubmit}
        >
          {isBuy ? 'Record buy' : 'Record sell'}
        </button>
      </div>

      <p className="mode-hint">
        Manual edits update your portfolio and become the active source for recommendations.
      </p>
      {message && (
        <div className="status-block">
          <CheckCircle2 size={18} />
          <span>{message}</span>
        </div>
      )}
    </section>
  );
}
