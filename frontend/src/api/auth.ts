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

  // Public password reset endpoints are disabled; admins reset passwords via admin UI.
};
