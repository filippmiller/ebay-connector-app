import api from '@/lib/apiClient';
import type { ManualParsedRow } from './Accounting2Page';

export function parseManualRawText(
  raw: string,
  setRows: (rows: ManualParsedRow[]) => void,
  setError: (msg: string | null) => void,
): void {
  const lines = raw
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);

  const rows: ManualParsedRow[] = [];
  let buffer: { date: string; descParts: string[] } | null = null;
  const dateRe = /^(\d{1,2})\/(\d{1,2})\s+(.+)$/;
  const dateAmountRe = /^(\d{1,2})\/(\d{1,2})\s+(.+?)\s+([\d,]+\.\d{2})$/;
  const amountOnlyRe = /^-?[\d,]+\.\d{2}$/;

  const currentYear = new Date().getFullYear();

  const flush = (descParts: string[], dateStr: string, amountStr: string) => {
    const [m, d] = dateStr.split('/').map((x) => parseInt(x, 10));
    const isoDate = `${currentYear}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    const desc = descParts.join(' ').replace(/\s+/g, ' ').trim();
    const normalizedDesc = desc.toUpperCase();
    const amount = amountStr.replace(/,/g, '');

    rows.push({
      id: rows.length + 1,
      date: isoDate,
      description: desc,
      amount,
      direction: 'credit',
      duplicate: false,
      _key: `${isoDate}|${normalizedDesc}|${amount}`,
    } as any);
  };

  for (const line of lines) {
    const dateAmountMatch = dateAmountRe.exec(line);
    if (dateAmountMatch) {
      const dateStr = `${dateAmountMatch[1]}/${dateAmountMatch[2]}`;
      const desc = dateAmountMatch[3];
      const amountStr = dateAmountMatch[4];
      flush([desc], dateStr, amountStr);
      buffer = null;
      continue;
    }

    const amountOnlyMatch = amountOnlyRe.exec(line);
    if (amountOnlyMatch && buffer) {
      flush(buffer.descParts, buffer.date, amountOnlyMatch[0]);
      buffer = null;
      continue;
    }

    const dateMatch = dateRe.exec(line);
    if (dateMatch) {
      // start new buffer; if previous buffer was hanging without amount, drop it
      const dateStr = `${dateMatch[1]}/${dateMatch[2]}`;
      const rest = dateMatch[3];
      buffer = { date: dateStr, descParts: [rest] };
      continue;
    }

    // continuation of description
    if (buffer) {
      buffer.descParts.push(line);
    }
  }

  if (rows.length === 0) {
    setError('Не удалось распарсить ни одной строки. Проверьте формат текста.');
    setRows([]);
    return;
  }

  // dedupe inside the pasted set by date+normalized description+amount
  const seen = new Set<string>();
  const deduped: ManualParsedRow[] = [];
  for (const row of rows) {
    const key = (row as any)._key as string;
    if (seen.has(key)) {
      deduped.push({ ...row, duplicate: true });
    } else {
      seen.add(key);
      deduped.push({ ...row, duplicate: false });
    }
  }

  setError(null);
  setRows(deduped);
}

export async function saveManualStatementImpl(
  rows: ManualParsedRow[],
  options: {
    bankName: string;
    bankCode: string;
    accountLast4: string;
    currency: string;
    periodStart: string;
    periodEnd: string;
    opening: string;
    closing: string;
    commit: boolean;
  },
): Promise<number> {
  const {
    bankName,
    bankCode,
    accountLast4,
    currency,
    periodStart,
    periodEnd,
    opening,
    closing,
    commit,
  } = options;

  if (!periodStart || !periodEnd) {
    throw new Error('Period start and end are required');
  }

  if (!rows.length) {
    throw new Error('No rows to save');
  }

  const payload = {
    bank_name: bankName,
    bank_code: bankCode || null,
    account_last4: accountLast4 || null,
    currency,
    period_start: periodStart,
    period_end: periodEnd,
    opening_balance: opening ? Number(opening) : null,
    closing_balance: closing ? Number(closing) : null,
    transactions: rows
      .filter((r) => !r.duplicate)
      .map((r) => ({
        date: r.date,
        description: r.description,
        direction: r.direction,
        amount: Number(r.amount),
      })),
  };

  const { data } = await api.post<{ id: number }>(
    '/accounting2/bank-statements/manual-from-text',
    payload,
  );

  const id = data.id;

  if (commit && id) {
    await api.post(`/accounting/bank-statements/${id}/commit-rows`, {
      commit_all_non_ignored: true,
    });
  }

  return id;
}
