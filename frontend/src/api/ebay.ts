import { apiClient } from './client';
import type { EbayConnectionStatus, EbayLog } from '../types';

export const ebayApi = {
  async startAuth(redirectUri: string, environment: 'sandbox' | 'production' = 'sandbox', scopes?: string[]): Promise<{ authorization_url: string; state: string }> {
    const params = new URLSearchParams({ 
      redirect_uri: redirectUri,
      environment: environment
    });
    const body = scopes ? { scopes } : {};
    return apiClient.post(`/ebay/auth/start?${params}`, body);
  },

  async handleCallback(code: string, redirectUri: string, environment: string = 'sandbox', state?: string): Promise<{ message: string; expires_in: number }> {
    const params = new URLSearchParams({ 
      redirect_uri: redirectUri,
      environment: environment
    });
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

  async testFetchOrders(limit: number = 10): Promise<any> {
    return apiClient.get(`/ebay/test/orders?limit=${limit}`);
  },

  async testFetchTransactions(limit: number = 10): Promise<any> {
    return apiClient.get(`/ebay/test/transactions?limit=${limit}`);
  },

  async syncAllOrders(): Promise<any> {
    return apiClient.post('/ebay/sync/orders');
  },

  async getSyncJobs(limit: number = 10): Promise<any> {
    return apiClient.get(`/ebay/sync/jobs?limit=${limit}`);
  },

  async getOrders(limit: number = 100, offset: number = 0): Promise<any> {
    return apiClient.get(`/ebay/orders?limit=${limit}&offset=${offset}`);
  },
};
