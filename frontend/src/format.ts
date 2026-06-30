export const moneyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 2,
});

export const numberFormatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 2,
});

export const percentFormatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 2,
});

export function formatMoney(value: number): string {
  return moneyFormatter.format(value);
}

export function formatNumber(value: number): string {
  return numberFormatter.format(value);
}

export function formatPercent(value: number): string {
  return `${percentFormatter.format(value)}%`;
}

export function formatDateTime(value: string): string {
  return new Date(value).toLocaleString('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}
