import { apiClient } from './client';
import type { EbayConnectionStatus, EbayLog, EbayConnectLog } from '../types';

export const ebayApi = {
  async startAuth(redirectUri: string, environment: 'sandbox' | 'production' = 'sandbox', scopes?: string[]): Promise<{ authorization_url: string; state: string }> {
    const params = new URLSearchParams({ 
      redirect_uri: redirectUri,
      environment: environment
    });
    const body = scopes ? { scopes } : {};
    const response = await apiClient.post(`/ebay/auth/start?${params}`, body);
    return response.data;
  },

  async handleCallback(code: string, redirectUri: string, environment: string = 'sandbox', state?: string): Promise<{ message: string; expires_in: number }> {
    const params = new URLSearchParams({ 
      redirect_uri: redirectUri,
      environment: environment
    });
    const response = await apiClient.post(`/ebay/auth/callback?${params}`, { code, state });
    return response.data;
  },

  async getStatus(): Promise<EbayConnectionStatus> {
    const response = await apiClient.get<EbayConnectionStatus>('/ebay/status');
    return response.data;
  },

  async disconnect(): Promise<{ message: string }> {
    const response = await apiClient.post('/ebay/disconnect');
    return response.data;
  },

  async getLogs(limit: number = 100): Promise<{ logs: EbayLog[]; total: number }> {
    const response = await apiClient.get<{ logs: EbayLog[]; total: number }>(`/ebay/logs?limit=${limit}`);
    return response.data;
  },

  async clearLogs(): Promise<{ message: string }> {
    const response = await apiClient.delete('/ebay/logs');
    return response.data;
  },

  async getConnectLogs(environment?: 'sandbox' | 'production', limit: number = 100): Promise<{ logs: EbayConnectLog[] }> {
    const params = new URLSearchParams();
    if (environment) params.set('environment', environment);
    params.set('limit', String(limit));
    const response = await apiClient.get<{ logs: EbayConnectLog[] }>(`/ebay/connect/logs?${params.toString()}`);
    return response.data;
  },

  async testFetchOrders(limit: number = 10): Promise<any> {
    const response = await apiClient.get(`/ebay/test/orders?limit=${limit}`);
    return response.data;
  },

  async testFetchTransactions(limit: number = 10): Promise<any> {
    const response = await apiClient.get(`/ebay/test/transactions?limit=${limit}`);
    return response.data;
  },

  async syncAllOrders(environment?: 'sandbox' | 'production'): Promise<any> {
    const params = environment ? `?environment=${environment}` : '';
    const response = await apiClient.post(`/ebay/sync/orders${params}`);
    return response.data;
  },

  async syncAllTransactions(environment?: 'sandbox' | 'production'): Promise<any> {
    const params = environment ? `?environment=${environment}` : '';
    const response = await apiClient.post(`/ebay/sync/transactions${params}`);
    return response.data;
  },

  async syncAllDisputes(environment?: 'sandbox' | 'production'): Promise<any> {
    const params = environment ? `?environment=${environment}` : '';
    const response = await apiClient.post(`/ebay/sync/disputes${params}`);
    return response.data;
  },

  async syncAllOffers(environment?: 'sandbox' | 'production'): Promise<any> {
    const params = environment ? `?environment=${environment}` : '';
    const response = await apiClient.post(`/ebay/sync/offers${params}`);
    return response.data;
  },

  async syncAllInventory(environment?: 'sandbox' | 'production'): Promise<any> {
    const params = environment ? `?environment=${environment}` : '';
    const response = await apiClient.post(`/ebay/sync/inventory${params}`);
    return response.data;
  },

  async getSyncJobs(limit: number = 10): Promise<any> {
    const response = await apiClient.get(`/ebay/sync/jobs?limit=${limit}`);
    return response.data;
  },

  async getOrders(limit: number = 100, offset: number = 0): Promise<any> {
    const response = await apiClient.get(`/ebay/orders?limit=${limit}&offset=${offset}`);
    return response.data;
  },
};
