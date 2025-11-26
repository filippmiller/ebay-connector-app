import { FormEvent, useEffect, useState } from 'react';

import FixedHeader from '@/components/FixedHeader';
import { Card } from '@/components/ui/card';
import api from '@/lib/apiClient';

interface OpenAiProviderDto {
  provider_code: string;
  name: string;
  has_api_key: boolean;
  model_default: string | null;
}

const MODEL_OPTIONS = ['gpt-4.1-mini', 'gpt-4.1', 'o3-mini'];

export default function AdminAiSettingsPage() {
  const [provider, setProvider] = useState<OpenAiProviderDto | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [modelDefault, setModelDefault] = useState('gpt-4.1-mini');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  const loadProvider = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await api.get<OpenAiProviderDto>('/api/integrations/ai-provider/openai');
      const data = resp.data;
      setProvider(data);
      if (data.model_default) {
        setModelDefault(data.model_default);
      }
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Не удалось загрузить настройки OpenAI';
      setError(String(msg));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadProvider();
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setFlash(null);
    try {
      await api.post<OpenAiProviderDto>('/api/integrations/ai-provider/openai', {
        api_key: apiKeyInput || null,
        model_default: modelDefault,
      });
      setApiKeyInput('');
      setFlash('Настройки сохранены. Новый ключ будет использоваться для AI-запросов.');
      void loadProvider();
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || 'Не удалось сохранить настройки OpenAI';
      setError(String(msg));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <FixedHeader />
      <div className="pt-16 px-4 py-6 max-w-3xl w-full mx-auto flex-1 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">AI Settings</h1>
            <p className="text-sm text-gray-600 max-w-2xl">
              Конфигурация провайдера OpenAI: API key и модель по умолчанию для будущих AI-подсказок
              и обучения на базе email-пар.
            </p>
          </div>
          {loading && <div className="text-xs text-gray-500">Loading…</div>}
        </div>

        {error && (
          <div className="text-xs text-red-700 border border-red-200 bg-red-50 rounded px-2 py-1" role="alert">
            {error}
          </div>
        )}
        {flash && (
          <div className="text-xs text-green-700 border border-green-200 bg-green-50 rounded px-2 py-1" role="status">
            {flash}
          </div>
        )}

        <Card className="p-4">
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="space-y-1 text-xs">
              <label className="font-semibold text-gray-700" htmlFor="openai-api-key">
                OpenAI API key
              </label>
              <input
                id="openai-api-key"
                type="password"
                className="w-full border rounded px-2 py-1 text-xs bg-white"
                placeholder={provider?.has_api_key ? '•••••••• (ключ уже задан, введите новый для замены)' : ''}
                autoComplete="off"
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
              />
              <p className="text-[11px] text-gray-500">
                Ключ хранится в зашифрованном виде в базе данных. Мы никогда не показываем его в явном виде.
                Оставьте поле пустым, если не хотите менять текущий ключ.
              </p>
            </div>

            <div className="space-y-1 text-xs">
              <label className="font-semibold text-gray-700" htmlFor="openai-model-default">
                Default model
              </label>
              <select
                id="openai-model-default"
                className="w-full border rounded px-2 py-1 text-xs bg-white"
                value={modelDefault}
                onChange={(e) => setModelDefault(e.target.value)}
              >
                {MODEL_OPTIONS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
              <p className="text-[11px] text-gray-500">
                Эта модель будет использоваться по умолчанию для генерации SQL, черновиков ответов и
                последующих AI-функций.
              </p>
            </div>

            <div className="pt-2 flex items-center justify-end gap-2 text-xs">
              <button
                type="submit"
                disabled={saving}
                className="px-3 py-1.5 rounded bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-60"
              >
                {saving ? 'Saving…' : 'Save settings'}
              </button>
            </div>
          </form>
        </Card>
      </div>
    </div>
  );
}