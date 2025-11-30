import { useMemo, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import api from '@/lib/apiClient';
import { AppDataGrid, type AppDataGridColumnState } from '@/components/datagrid/AppDataGrid';
import type { GridColumnMeta } from '@/components/DataGridPage';
import { useSpeechInput } from '@/hooks/useSpeechInput';

interface AiGridColumnDto {
  field: string;
  headerName: string;
  type?: string | null;
  width?: number | null;
}

interface AiQueryResponseDto {
  columns: AiGridColumnDto[];
  rows: Record<string, any>[];
  sql: string;
}

const GRID_KEY = 'admin_ai_grid';
const LAYOUT_STORAGE_KEY = `grid_layout_${GRID_KEY}`;

interface StoredLayout {
  order: string[];
  widths: Record<string, number>;
}

export default function AdminAiGridPage() {
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [columns, setColumns] = useState<AppDataGridColumnState[]>([]);
  const [rows, setRows] = useState<Record<string, any>[]>([]);
  const [columnMetaByName, setColumnMetaByName] = useState<Record<string, GridColumnMeta>>({});
  const [lastSql, setLastSql] = useState<string | null>(null);

  const { supportsSpeech, isRecording, error: voiceError, startDictation } = useSpeechInput();

  const applyStoredLayout = useMemo(
    () =>
      (incoming: AppDataGridColumnState[]): AppDataGridColumnState[] => {
        if (!incoming.length) return incoming;
        let stored: StoredLayout | null = null;
        try {
          const raw = window.localStorage.getItem(LAYOUT_STORAGE_KEY);
          if (raw) {
            stored = JSON.parse(raw) as StoredLayout;
          }
        } catch {
          stored = null;
        }

        if (!stored || !stored.order || stored.order.length === 0) {
          return incoming;
        }

        const byName = new Map<string, AppDataGridColumnState>();
        incoming.forEach((c) => {
          byName.set(c.name, { ...c });
        });

        const ordered: AppDataGridColumnState[] = [];
        for (const name of stored.order) {
          const col = byName.get(name);
          if (!col) continue;
          const width = stored.widths?.[name];
          ordered.push({ ...col, width: typeof width === 'number' && width > 0 ? width : col.width });
          byName.delete(name);
        }

        // Append any new columns that were not in the stored layout.
        byName.forEach((col) => {
          ordered.push(col);
        });

        return ordered;
      },
    [],
  );

  const handleRunQuery = async () => {
    const trimmed = prompt.trim();
    if (!trimmed) {
      setError('Введите запрос на естественном языке (например: "Покажи письма с плохой упаковкой")');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const resp = await api.post<AiQueryResponseDto>('/api/admin/ai/query', { prompt: trimmed });
      const data = resp.data;

      const baseCols: AppDataGridColumnState[] = data.columns.map((c) => ({
        name: c.field,
        label: c.headerName || c.field,
        width: c.width && c.width > 0 ? c.width : 180,
      }));
      const nextCols = applyStoredLayout(baseCols);
      setColumns(nextCols);

      const meta: Record<string, GridColumnMeta> = {};
      data.columns.forEach((c) => {
        meta[c.field] = {
          name: c.field,
          label: c.headerName || c.field,
          type: (c.type as any) || 'string',
          width_default: c.width || 180,
          sortable: true,
        };
      });
      setColumnMetaByName(meta);

      setRows(data.rows || []);
      setLastSql(data.sql || null);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e.message || 'Не удалось выполнить AI-запрос';
      setError(String(msg));
      setRows([]);
      setColumns([]);
      setColumnMetaByName({});
    } finally {
      setLoading(false);
    }
  };

  const handleVoiceInput = () => {
    startDictation((text) => {
      setPrompt((prev) => (prev ? `${prev} ${text}` : text));
    });
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <FixedHeader />
      <div className="pt-16 px-4 py-6 max-w-6xl w-full mx-auto flex-1 flex flex-col gap-4">
        <h1 className="text-2xl font-bold">Admin AI Grid Playground</h1>
        <p className="text-sm text-gray-600 max-w-3xl">
          Введите запрос на естественном языке, я превращу его в безопасный SQL по whitelisted-таблицам
          (сообщения, кейсы, покупки) и отрисую результат в гриде ниже. Примеры:
          "Покажи письма, где жалуются на плохую упаковку" или
          "Покажи компьютеры, которые окупились быстрее всего".
        </p>

        <Card className="p-4 space-y-3">
          <label className="block text-sm font-medium text-gray-700">AI-запрос</label>
          <Textarea
            rows={3}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Например: Покажи письма, где жалуются, что деталь разбилась из-за плохой упаковки"
          />
          <div className="flex items-center justify-between gap-3">
            <div className="text-xs text-gray-500">
              Я сгенерирую только SELECT-запрос и выполню его в read-only режиме по безопасным таблицам.
            </div>
            <div className="flex items-center gap-2">
              {supportsSpeech && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleVoiceInput}
                  disabled={loading || isRecording}
                >
                  {isRecording ? 'Слушаю…' : 'Голосом'}
                </Button>
              )}
              <Button onClick={handleRunQuery} disabled={loading}>
                {loading ? 'Выполняю…' : 'Run AI Query'}
              </Button>
            </div>
          </div>
          {error && (
            <div className="text-xs text-red-600 whitespace-pre-wrap border border-red-200 bg-red-50 rounded px-2 py-1 mt-2">
              {error}
            </div>
          )}
          {voiceError && (
            <div className="text-xs text-red-600 whitespace-pre-wrap border border-red-200 bg-red-50 rounded px-2 py-1 mt-2">
              {voiceError}
            </div>
          )}
          {lastSql && (
            <div className="mt-2 text-xs text-gray-500 font-mono break-all">
              <span className="font-semibold mr-1">SQL:</span>
              {lastSql}
            </div>
          )}
        </Card>

        <Card className="flex-1 min-h-[300px] p-3 flex flex-col">
          <h2 className="text-sm font-semibold mb-2">Результат</h2>
          <div className="flex-1 min-h-[240px]">
            {columns.length === 0 ? (
              <div className="h-full flex items-center justify-center text-sm text-gray-500">
                Нет данных. Сначала выполните AI-запрос.
              </div>
            ) : (
              <AppDataGrid
                columns={columns}
                rows={rows}
                columnMetaByName={columnMetaByName}
                loading={loading}
                gridKey={GRID_KEY}
                gridTheme={null}
                onLayoutChange={({ order, widths }) => {
                  const payload: StoredLayout = { order, widths };
                  try {
                    window.localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(payload));
                  } catch {
                    // best-effort only
                  }
                }}
              />
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
