import { apiClient } from './client';
import type { User, LoginCredentials, RegisterData, AuthResponse } from '../types';

export const authApi = {
  async register(data: RegisterData): Promise<User> {
    const response = await apiClient.post<User>('/auth/register', data);
    return response.data;
  },

  async login(credentials: LoginCredentials): Promise<AuthResponse> {
    const response = await apiClient.post<AuthResponse>('/auth/login', credentials);
    return response.data;
  },

  async getCurrentUser(): Promise<User> {
    const response = await apiClient.get<User>('/auth/me');
    return response.data;
  },

  async requestPasswordReset(email: string): Promise<{ message: string; reset_token?: string }> {
    const response = await apiClient.post('/auth/password-reset/request', { email });
    return response.data;
  },

  async resetPassword(email: string, reset_token: string, new_password: string): Promise<{ message: string }> {
    const response = await apiClient.post('/auth/password-reset/confirm', { email, reset_token, new_password });
    return response.data;
  },
};
