export interface User {
  id: string;
  email: string;
  username: string;
  role: 'user' | 'admin';
  is_active: boolean;
  created_at: string;
  ebay_connected: boolean;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterData {
  email: string;
  username: string;
  password: string;
  role: 'user' | 'admin';
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export interface EbayLog {
  timestamp: string;
  event_type: string;
  description: string;
  request_data?: Record<string, any>;
  response_data?: Record<string, any>;
  status: string;
  error?: string;
}

export interface EbayConnectionStatus {
  connected: boolean;
  user_id?: string;
  expires_at?: string;
  scopes?: string[];
}
