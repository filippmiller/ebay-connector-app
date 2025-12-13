import { useEffect, useState } from 'react';
import FixedHeader from '@/components/FixedHeader';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import api from '@/lib/apiClient';

interface AiRuleDto {
  id: string;
  name: string;
  rule_sql: string;
  description?: string | null;
  created_at: string;
}

export default function AdminAiRulesPage() {
  const [rules, setRules] = useState<AiRuleDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [ruleSql, setRuleSql] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);

  const loadRules = async () => {
    try {
      setLoading(true);
      setError(null);
      const resp = await api.get<AiRuleDto[]>('/api/admin/ai/rules');
      setRules(resp.data || []);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e.message || 'Не удалось загрузить правила';
      setError(String(msg));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRules();
  }, []);

  const handleCreate = async () => {
    const trimmedName = name.trim();
    const trimmedSql = ruleSql.trim();
    if (!trimmedName || !trimmedSql) {
      setError('Нужно указать и имя правила, и SQL-условие.');
      return;
    }
    try {
      setLoading(true);
      setError(null);
      await api.post<AiRuleDto>('/api/admin/ai/rules', {
        name: trimmedName,
        rule_sql: trimmedSql,
        description: description.trim() || null,
      });
      setName('');
      setDescription('');
      setRuleSql('');
      await loadRules();
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e.message || 'Не удалось сохранить правило';
      setError(String(msg));
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateSql = async () => {
    const trimmedDescription = description.trim();
    if (!trimmedDescription) {
      setError('Сначала опишите правило на естественном языке.');
      return;
    }
    try {
      setPreviewLoading(true);
      setError(null);
      const resp = await api.post<{ rule_sql: string }>('/api/admin/ai/rules/preview', {
        description: trimmedDescription,
      });
      setRuleSql(resp.data.rule_sql || '');
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e.message || 'Не удалось сгенерировать SQL-условие';
      setError(String(msg));
    } finally {
      setPreviewLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <FixedHeader />
      <div className="pt-16 px-4 py-6 max-w-6xl w-full mx-auto flex-1 flex flex-col gap-4">
        <h1 className="text-2xl font-bold">Admin AI Rules</h1>
        <p className="text-sm text-gray-600 max-w-3xl">
          Здесь можно хранить переиспользуемые SQL-правила (условия), которые описывают, что такое
          "хорошая покупка", "быстрая окупаемость" и т.п. Эти правила будут использоваться позже
          в аналитике и мониторинге (снайпер, гриды и т.д.).
        </p>

        <Card className="p-4 space-y-3">
          <h2 className="text-sm font-semibold">Новое правило</h2>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <label className="block text-xs font-medium text-gray-600">Имя правила</label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Например: good_computer_100pct_60days"
              />
              <label className="block text-xs font-medium text-gray-600 mt-3">Описание (натуральный язык)</label>
              <Textarea
                rows={3}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Например: Компьютер считается хорошим, если profit_percentage >= 100 и days_to_recover <= 60."
              />
              <div className="flex justify-end mt-1">
                <Button variant="outline" size="sm" onClick={handleGenerateSql} disabled={previewLoading}>
                  {previewLoading ? 'Генерация…' : 'Generate SQL from Description'}
                </Button>
              </div>
            </div>
            <div className="space-y-2">
              <label className="block text-xs font-medium text-gray-600">SQL-условие (WHERE-фрагмент)</label>
              <Textarea
                rows={6}
                value={ruleSql}
                onChange={(e) => setRuleSql(e.target.value)}
                placeholder="Например: profit_percentage >= 100 AND days_to_recover <= 60"
              />
              <div className="text-[11px] text-gray-500">
                Это должно быть безопасное условие без UPDATE/DELETE/INSERT/DDL. Оно будет добавляться в WHERE.
              </div>
            </div>
          </div>
          {error && (
            <div className="text-xs text-red-600 whitespace-pre-wrap border border-red-200 bg-red-50 rounded px-2 py-1">
              {error}
            </div>
          )}
          <div className="flex justify-end">
            <Button onClick={handleCreate} disabled={loading}>
              {loading ? 'Сохраняю…' : 'Сохранить правило'}
            </Button>
          </div>
        </Card>

        <Card className="p-4 space-y-3 flex-1 overflow-hidden">
          <h2 className="text-sm font-semibold">Сохранённые правила</h2>
          {loading && rules.length === 0 ? (
            <div className="text-sm text-gray-500">Загрузка…</div>
          ) : rules.length === 0 ? (
            <div className="text-sm text-gray-500">Пока нет ни одного правила.</div>
          ) : (
            <div className="space-y-2 max-h-[320px] overflow-y-auto text-sm">
              {rules.map((r) => (
                <div
                  key={r.id}
                  className="border border-gray-200 rounded-md px-3 py-2 bg-white shadow-sm flex flex-col gap-1"
                >
                  <div className="flex justify-between items-center">
                    <div className="font-semibold text-xs text-gray-800">{r.name}</div>
                    <div className="text-[10px] text-gray-400 font-mono">{r.created_at}</div>
                  </div>
                  {r.description && (
                    <div className="text-xs text-gray-600 whitespace-pre-wrap">{r.description}</div>
                  )}
                  <div className="mt-1 text-[11px] text-gray-800 font-mono whitespace-pre-wrap break-all">
                    WHERE {r.rule_sql}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
