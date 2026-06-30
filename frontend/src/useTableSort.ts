import { useMemo, useState } from 'react';

export type SortDirection = 'asc' | 'desc';

export interface TableSort<Row> {
  sortedRows: Row[];
  sortKey: keyof Row;
  sortDirection: SortDirection;
  toggleSort: (key: keyof Row) => void;
}

function compareValues(left: unknown, right: unknown): number {
  if (left === right) {
    return 0;
  }
  if (left === null || left === undefined) {
    return 1;
  }
  if (right === null || right === undefined) {
    return -1;
  }
  if (typeof left === 'number' && typeof right === 'number') {
    return left - right;
  }
  return String(left).localeCompare(String(right));
}

export function useTableSort<Row>(
  rows: Row[],
  initialKey: keyof Row,
  initialDirection: SortDirection = 'desc',
): TableSort<Row> {
  const [sortKey, setSortKey] = useState<keyof Row>(initialKey);
  const [sortDirection, setSortDirection] = useState<SortDirection>(initialDirection);

  const sortedRows = useMemo(() => {
    const ordered = [...rows];
    ordered.sort((left, right) => {
      const comparison = compareValues(left[sortKey], right[sortKey]);
      return sortDirection === 'asc' ? comparison : -comparison;
    });
    return ordered;
  }, [rows, sortKey, sortDirection]);

  function toggleSort(key: keyof Row): void {
    if (key === sortKey) {
      setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortKey(key);
    setSortDirection('desc');
  }

  return { sortedRows, sortKey, sortDirection, toggleSort };
}
