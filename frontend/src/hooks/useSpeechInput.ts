import { useCallback, useEffect, useState } from 'react';

/**
 * useSpeechInput
 *
 * Лёгкий враппер над браузерным Web Speech API (SpeechRecognition).
 * Отвечает ТОЛЬКО за распознавание речи в текст на стороне браузера.
 *
 * Безопасность:
 * - Хук НИКОГДА не трогает OpenAI API и не знает про ваш API‑ключ.
 * - Вся обработка звука происходит в браузере (Chrome / Edge и т.д.).
 * - В приложение возвращается только готовый текст (transcript),
 *   который обрабатывается так же, как ввод из обычного текстового поля.
 */
export interface UseSpeechInputOptions {
  /**
   * Preferred language code. If не указано, будет выбрана на основе navigator.language.
   * Примеры: "ru-RU", "en-US".
   */
  language?: string;
}

export interface UseSpeechInputResult {
  /** Поддерживает ли текущий браузер Web Speech API. */
  supportsSpeech: boolean;
  /** Идёт ли сейчас запись / распознавание. */
  isRecording: boolean;
  /** Текст последней ошибки распознавания, если была. */
  error: string | null;
  /**
   * Запустить диктовку. Колбэк onText будет вызван с готовой строкой
   * (transcript), когда браузер закончит распознавание.
   */
  startDictation(onText: (text: string) => void): void;
}

/**
 * Пытаемся выбрать язык распознавания на основе настроек браузера.
 *
 * Приоритет такой:
 * 1) Если среди navigator.languages есть любой вариант "ru" — берём ru-RU.
 * 2) Иначе, если есть любой вариант "en" — берём en-US.
 * 3) Иначе падаем в fallback (по умолчанию ru-RU).
 */
function pickPreferredLanguage(fallback: string = 'ru-RU'): string {
  try {
    const rawList = (navigator as any).languages || [navigator.language];
    const langs = (rawList || []).filter(Boolean).map((l: string) => l.toLowerCase());

    // 1) Если есть любой вариант русского — всегда берём его (русский по умолчанию).
    if (langs.some((l: string) => l.startsWith('ru'))) return 'ru-RU';
    // 2) Иначе, если есть английский — берём английский.
    if (langs.some((l: string) => l.startsWith('en'))) return 'en-US';
  } catch {
    // игнорируем и используем fallback ниже
  }
  return fallback;
}

/**
 * Преобразует BCP-47 код (ru-RU / en-US) в короткий хинт для Deepgram.
 */
function toDeepgramLanguageHint(langBcp47: string): string | undefined {
  const lower = langBcp47.toLowerCase();
  if (lower.startsWith('ru')) return 'ru';
  if (lower.startsWith('en')) return 'en';
  return undefined;
}

/**
 * Основной React‑хук для голосового ввода.
 *
 * Текущая реализация:
 * - Пишет короткий отрывок через MediaRecorder (если доступен) и
 *   отправляет его на backend /api/ai/speech/deepgram.
 * - Backend вызывает Deepgram STT и возвращает текст.
 * - API‑ключ Deepgram хранится только на сервере.
 */
export function useSpeechInput(options: UseSpeechInputOptions = {}): UseSpeechInputResult {
  const [supportsSpeech, setSupportsSpeech] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      const hasMediaRecorder =
        typeof (window as any).MediaRecorder !== 'undefined' &&
        navigator.mediaDevices &&
        typeof navigator.mediaDevices.getUserMedia === 'function';
      setSupportsSpeech(Boolean(hasMediaRecorder));
    } catch {
      setSupportsSpeech(false);
    }
  }, []);

  const startDictation = useCallback(
    (onText: (text: string) => void) => {
      if (!supportsSpeech) {
        setError('Браузер не поддерживает MediaRecorder для голосового ввода.');
        return;
      }

      const recordAndSend = async () => {
        try {
          setIsRecording(true);
          setError(null);

          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          const mimeType = 'audio/webm';
          const MediaRecorderCtor = (window as any).MediaRecorder as typeof MediaRecorder;
          const recorder = new MediaRecorderCtor(stream, { mimeType });

          const chunks: BlobPart[] = [];

          recorder.ondataavailable = (event: BlobEvent) => {
            if (event.data && event.data.size > 0) {
              chunks.push(event.data);
            }
          };

          recorder.start();

          // Автоматически останавливаем запись через 10 секунд
          const MAX_MS = 10000;
          const stopTimeout = setTimeout(() => {
            if (recorder.state === 'recording') {
              recorder.stop();
            }
          }, MAX_MS);

          recorder.onstop = async () => {
            clearTimeout(stopTimeout);
            stream.getTracks().forEach((t) => t.stop());

            const blob = new Blob(chunks, { type: mimeType });
            if (blob.size === 0) {
              setIsRecording(false);
              setError('Не удалось записать звук. Попробуйте ещё раз.');
              return;
            }

            try {
              const form = new FormData();
              form.append('file', blob, 'speech.webm');

              const langBcp47 = options.language || pickPreferredLanguage('ru-RU');
              const dgLang = toDeepgramLanguageHint(langBcp47);
              if (dgLang) {
                form.append('language', dgLang);
              }

              const { default: api } = await import('@/lib/apiClient');
              const resp = await api.post<{ text: string }>('/ai/speech/deepgram', form, {
                headers: { 'Content-Type': 'multipart/form-data' },
              });

              const text = (resp.data?.text || '').trim();
              if (text) {
                onText(text);
              } else {
                setError('Речь распознана, но текст пустой. Попробуйте сказать чуть медленнее.');
              }
            } catch (e: any) {
              const msg =
                e?.response?.data?.detail ||
                e?.message ||
                'Не удалось отправить аудио на сервер для распознавания речи.';
              setError(String(msg));
            } finally {
              setIsRecording(false);
            }
          };
        } catch (e: any) {
          setIsRecording(false);
          if (e?.name === 'NotAllowedError') {
            setError('Доступ к микрофону запрещён браузером. Разрешите доступ в настройках.');
          } else {
            setError(e?.message || 'Не удалось получить доступ к микрофону.');
          }
        }
      };

      void recordAndSend();
    },
    [supportsSpeech, options.language],
  );

  return { supportsSpeech, isRecording, error, startDictation };
}
