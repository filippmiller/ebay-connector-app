import { apiClient } from './client';
import type { EbayConnectionStatus, EbayLog } from '../types';

export const ebayApi = {
  async startAuth(redirectUri: string, scopes?: string[]): Promise<{ authorization_url: string; state: string }> {
    const params = new URLSearchParams({ redirect_uri: redirectUri });
    const body = scopes ? { scopes } : {};
    return apiClient.post(`/ebay/auth/start?${params}`, body);
  },

  async handleCallback(code: string, redirectUri: string, state?: string): Promise<{ message: string; expires_in: number }> {
    const params = new URLSearchParams({ redirect_uri: redirectUri });
    return apiClient.post(`/ebay/auth/callback?${params}`, { code, state });
  },

  async getStatus(): Promise<EbayConnectionStatus> {
    return apiClient.get<EbayConnectionStatus>('/ebay/status');
  },

  async disconnect(): Promise<{ message: string }> {
    return apiClient.post('/ebay/disconnect');
  },

  async getLogs(limit: number = 100): Promise<{ logs: EbayLog[]; total: number }> {
    return apiClient.get<{ logs: EbayLog[]; total: number }>(`/ebay/logs?limit=${limit}`);
  },

  async clearLogs(): Promise<{ message: string }> {
    return apiClient.delete('/ebay/logs');
  },
};
