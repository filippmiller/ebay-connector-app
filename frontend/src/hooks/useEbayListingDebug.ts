import { useCallback, useState } from 'react';
import { runEbayListingDebug, type WorkerDebugTrace } from '@/api/ebayListingWorker';
import { useToast } from '@/hooks/use-toast';

export interface UseEbayListingDebugResult {
  isDebugEnabled: boolean;
  runDebugForIds: (
    ids: number[],
    opts?: { dryRun?: boolean; maxItems?: number },
  ) => Promise<void>;
  /**
   * Run the worker in "auto-candidates" mode (no explicit ids).
   *
   * The backend will select parts_detail rows by status/flags only,
   * up to maxItems. This is intended for dev/QA bulk runs.
   */
  runDebugForAutoCandidates: (
    opts?: { dryRun?: boolean; maxItems?: number },
  ) => Promise<void>;
  trace: WorkerDebugTrace | null;
  open: boolean;
  setOpen: (open: boolean) => void;
  loading: boolean;
  error: string | null;
}

/**
 * Reusable hook for running the eBay listing debug worker and wiring
 * its trace into the shared WorkerDebugTerminalModal.
 *
 * - Enabled only when VITE_DEBUG_EBAY_LISTING === 'true'.
 * - Never breaks the surrounding UI flow: all errors are surfaced via
 *   toast + `error` state but are otherwise swallowed.
 */
export function useEbayListingDebug(): UseEbayListingDebugResult {
  const { toast } = useToast();
  const isDebugEnabled = import.meta.env.VITE_DEBUG_EBAY_LISTING === 'true';

  const [trace, setTrace] = useState<WorkerDebugTrace | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runDebugForIds = useCallback<
    UseEbayListingDebugResult['runDebugForIds']
  >(
    async (ids, opts) => {
      if (!isDebugEnabled) {
        // In non-debug environments this is a no-op.
        return;
      }

      const uniqueIds = Array.from(
        new Set(
          (ids || [])
            .map((id) => Number(id))
            .filter((id) => Number.isFinite(id) && id > 0),
        ),
      );

      if (!uniqueIds.length) {
        return;
      }

      setLoading(true);
      setError(null);

      try {
        const resp = await runEbayListingDebug({
          ids: uniqueIds,
          dry_run: opts?.dryRun ?? false,
          max_items: opts?.maxItems ?? 50,
        });
        setTrace(resp.trace);
        setOpen(true);
      } catch (err: any) {
        const detail = err?.response?.data?.detail ?? err?.message ?? 'Listing debug worker failed';
        const message = String(detail);
        setError(message);
        toast({
          title: 'Listing debug worker error',
          description: message,
          variant: 'destructive',
        });
      } finally {
        setLoading(false);
      }
    },
    [isDebugEnabled, toast],
  );

  const runDebugForAutoCandidates = useCallback<
    UseEbayListingDebugResult['runDebugForAutoCandidates']
  >(
    async (opts) => {
      if (!isDebugEnabled) {
        // In non-debug environments this is a no-op.
        return;
      }

      setLoading(true);
      setError(null);

      try {
        const resp = await runEbayListingDebug({
          // No ids field → backend auto-selects by status/flags only.
          dry_run: opts?.dryRun ?? false,
          max_items: opts?.maxItems ?? 50,
        });
        setTrace(resp.trace);
        setOpen(true);
      } catch (err: any) {
        const detail = err?.response?.data?.detail ?? err?.message ?? 'Listing debug worker failed';
        const message = String(detail);
        setError(message);
        toast({
          title: 'Listing debug worker error',
          description: message,
          variant: 'destructive',
        });
      } finally {
        setLoading(false);
      }
    },
    [isDebugEnabled, toast],
  );

  return {
    isDebugEnabled,
    runDebugForIds,
    runDebugForAutoCandidates,
    trace,
    open,
    setOpen,
    loading,
    error,
  };
}
