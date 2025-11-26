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
    if (langs.some((l) => l.startsWith('ru'))) return 'ru-RU';
    // 2) Иначе, если есть английский — берём английский.
    if (langs.some((l) => l.startsWith('en'))) return 'en-US';
  } catch {
    // игнорируем и используем fallback ниже
  }
  return fallback;
}

/**
 * Основной React‑хук для голосового ввода.
 *
 * Пример использования:
 *
 *   const { supportsSpeech, isRecording, error, startDictation } = useSpeechInput();
 *
 *   const handleVoice = () => {
 *     startDictation((text) => setPrompt(prev => prev ? prev + ' ' + text : text));
 *   };
 */
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
        // Если язык явно не передан, пытаемся угадать его из настроек браузера,
        // отдавая приоритет русскому (ru-RU), затем английскому (en-US).
        const lang = options.language || pickPreferredLanguage('ru-RU');
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