import { useCallback, useEffect, useState } from 'react';

/**
 * useSpeechInput
 *
 * Lightweight wrapper around the browser Web Speech API (SpeechRecognition).
 *
 * Security considerations:
 * - This hook NEVER exposes any API keys or talks to OpenAI directly.
 * - All recognition happens inside the browser via the underlying engine
 *   (Chrome / Edge etc.). Our backend не участвует в голосовом вводе.
 * - Используем только текстовый результат (transcript), который вы уже
 *   затем можете отправлять на backend так же, как обычный текст из input.
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

export function useSpeechInput(options: UseSpeechInputOptions = {}): UseSpeechInputResult {
  const [supportsSpeech, setSupportsSpeech] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    try {
      const SpeechRecognition =
        (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      setSupportsSpeech(Boolean(SpeechRecognition));
    } catch {
      setSupportsSpeech(false);
    }
  }, []);

  const startDictation = useCallback(
    (onText: (text: string) => void) => {
      try {
        const SpeechRecognition =
          (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        if (!SpeechRecognition) {
          setError('Распознавание речи не поддерживается в этом браузере.');
          return;
        }

        const recognition = new SpeechRecognition();
        const lang = options.language || (navigator.language?.startsWith('en') ? 'en-US' : 'ru-RU');
        recognition.lang = lang;
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;

        setIsRecording(true);
        setError(null);

        recognition.onresult = (event: any) => {
          const transcript = event.results?.[0]?.[0]?.transcript as string | undefined;
          if (transcript) {
            onText(transcript);
          }
        };

        recognition.onerror = (event: any) => {
          const msg = event?.error === 'not-allowed'
            ? 'Доступ к микрофону запрещён браузером.'
            : 'Ошибка распознавания речи.';
          setError(msg);
        };

        recognition.onend = () => {
          setIsRecording(false);
        };

        recognition.start();
      } catch (e: any) {
        setIsRecording(false);
        setError(e?.message || 'Не удалось запустить распознавание речи.');
      }
    },
    [options.language],
  );

  return { supportsSpeech, isRecording, error, startDictation };
}