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

export interface EbayConnectLog {
  id: string;
  user_id?: string;
  environment: string;
  action: string;
  request?: {
    method?: string;
    url?: string;
    headers?: Record<string, any>;
    body?: any;
    query?: Record<string, any>;
  };
  response?: {
    status?: number;
    headers?: Record<string, any>;
    body?: any;
  };
  error?: string;
  created_at: string;
}

export interface EbayConnectionStatus {
  connected: boolean;
  user_id?: string;
  expires_at?: string;
  scopes?: string[];
}
