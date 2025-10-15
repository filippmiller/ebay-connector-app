import { apiClient } from './client';
import type { User, LoginCredentials, RegisterData, AuthResponse } from '../types';

export const authApi = {
  async register(data: RegisterData): Promise<User> {
    return apiClient.post<User>('/auth/register', data);
  },

  async login(credentials: LoginCredentials): Promise<AuthResponse> {
    return apiClient.post<AuthResponse>('/auth/login', credentials);
  },

  async getCurrentUser(): Promise<User> {
    return apiClient.get<User>('/auth/me');
  },

  async requestPasswordReset(email: string): Promise<{ message: string; reset_token?: string }> {
    return apiClient.post('/auth/password-reset/request', { email });
  },

  async resetPassword(email: string, reset_token: string, new_password: string): Promise<{ message: string }> {
    return apiClient.post('/auth/password-reset/confirm', { email, reset_token, new_password });
  },
};
