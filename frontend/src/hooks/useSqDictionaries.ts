import { useEffect, useState } from 'react';
import api from '@/lib/apiClient';

export interface InternalCategoryDto {
  id: number;
  code: string;
  label: string;
}

export interface ShippingGroupDto {
  id: number;
  code: string;
  label: string;
}

export interface ConditionDto {
  id: number;
  code: string;
  label: string;
}

export interface ListingTypeDto {
  code: string;
  label: string;
}

export interface ListingDurationDto {
  code: string;
  label: string;
  days: number | null;
}

export interface SiteDto {
  code: string;
  label: string;
  site_id: number;
}

export interface EbayBusinessPolicyDto {
  id: string;
  policy_type: 'SHIPPING' | 'PAYMENT' | 'RETURN';
  policy_id: string;
  policy_name: string;
  policy_description?: string | null;
  is_default: boolean;
  is_active: boolean;
  sort_order: number;
}

export interface EbayBusinessPoliciesResponseDto {
  shipping: EbayBusinessPolicyDto[];
  payment: EbayBusinessPolicyDto[];
  return: EbayBusinessPolicyDto[];
}

export interface EbayBusinessPoliciesDefaultsDto {
  shipping_policy_id?: string | null;
  payment_policy_id?: string | null;
  return_policy_id?: string | null;
}

export interface DictionariesResponse {
  internal_categories: InternalCategoryDto[];
  shipping_groups: ShippingGroupDto[];
  conditions: ConditionDto[];
  listing_types: ListingTypeDto[];
  listing_durations: ListingDurationDto[];
  sites: SiteDto[];
  ebay_business_policies: EbayBusinessPoliciesResponseDto;
  ebay_business_policy_defaults: EbayBusinessPoliciesDefaultsDto;
}

export interface UseSqDictionariesResult {
  loading: boolean;
  error: string | null;
  data: DictionariesResponse | null;
}

// Simple in-memory cache shared across hook instances so that SQ dictionaries
// are fetched only once per page load. This avoids repeated "Loading…"/
// re-render cycles when multiple components need the same lookups.
let cachedDictionaries: DictionariesResponse | null = null;
let inflightPromise: Promise<DictionariesResponse> | null = null;

export function useSqDictionaries(): UseSqDictionariesResult {
  const [loading, setLoading] = useState<boolean>(!cachedDictionaries);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<DictionariesResponse | null>(cachedDictionaries);

  useEffect(() => {
    // If we already have cached data, expose it immediately without hitting
    // the network again.
    if (cachedDictionaries) {
      setData(cachedDictionaries);
      setLoading(false);
      return;
    }

    let cancelled = false;

    if (!inflightPromise) {
      inflightPromise = api
        .get<DictionariesResponse>('/api/sq/dictionaries')
        .then((resp) => resp.data)
        .catch((e: any) => {
          // Surface error to all subscribers; cache remains null so callers can
          // retry by remounting if needed.
          const message = e?.response?.data?.detail || e?.message || 'Failed to load SQ dictionaries';
          if (!cancelled) {
            setError(message);
          }
          throw e;
        });
    }

    setLoading(true);
    setError(null);

    inflightPromise
      .then((result) => {
        if (cancelled) return;
        cachedDictionaries = result;
        setData(result);
        setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return { loading, error, data };
}
