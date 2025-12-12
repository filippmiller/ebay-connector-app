import axios, { AxiosError, InternalAxiosRequestConfig, AxiosResponse } from "axios";

const getBaseURL = () => {
  // NEVER use Fly.dev or devinapps.com - we use Railway backend via Cloudflare proxy
  // Only check environment variables, otherwise use /api (Cloudflare Pages proxy)
  
  // Debug: Log ALL environment variables to see what's set
  console.log('[API] Environment check:', {
    VITE_API_BASE_URL: import.meta.env.VITE_API_BASE_URL || '(not set)',
    VITE_API_URL: import.meta.env.VITE_API_URL || '(not set)',
    VITE_API_PREFIX: import.meta.env.VITE_API_PREFIX || '(not set)',
    MODE: import.meta.env.MODE,
    PROD: import.meta.env.PROD,
    DEV: import.meta.env.DEV
  });
  
  const ensureApiPrefix = (url: string) => {
    // Our backend routes are mounted under /api (FastAPI router prefixes).
    // In some deployments, a full base URL is injected (e.g. Railway) without the /api suffix,
    // which causes client requests like /accounting/... to 404. Normalize here.
    const u = (url || '').replace(/\s+/g, '');
    if (!u) return u;

    // If already points to /api, keep as-is
    if (u.endsWith('/api') || u.endsWith('/api/')) return u.replace(/\/$/, '');

    // Otherwise append /api
    return `${u.replace(/\/$/, '')}/api`;
  };

  if (import.meta.env.VITE_API_BASE_URL) {
    console.error('[API] ❌ VITE_API_BASE_URL is set:', import.meta.env.VITE_API_BASE_URL);
    console.error('[API] ❌ This will bypass Cloudflare proxy!');
    console.error('[API] ❌ DELETE this variable in Cloudflare Pages → Settings → Environment Variables');
    return ensureApiPrefix(import.meta.env.VITE_API_BASE_URL);
  }
  
  if (import.meta.env.VITE_API_URL) {
    console.error('[API] ❌ VITE_API_URL is set:', import.meta.env.VITE_API_URL);
    console.error('[API] ❌ This will bypass Cloudflare proxy!');
    console.error('[API] ❌ DELETE this variable in Cloudflare Pages → Settings → Environment Variables');
    return ensureApiPrefix(import.meta.env.VITE_API_URL);
  }
  
  if (import.meta.env.VITE_API_PREFIX) {
    console.warn('[API] ⚠️ VITE_API_PREFIX is set:', import.meta.env.VITE_API_PREFIX);
    return import.meta.env.VITE_API_PREFIX;
  }
  
  // Default: use /api which routes through Cloudflare Pages Function proxy to Railway
  console.log('[API] ✅ Using /api (Cloudflare proxy -> Railway backend)');
  return "/api";
};

const api = axios.create({
  baseURL: getBaseURL(),
  withCredentials: false,
  timeout: 30000, // Increased to 30s to handle cold starts (CF Functions + Railway backend)
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem("auth_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error: AxiosError) => {
    const status = error?.response?.status;
    const errorData = error?.response?.data as any; // Type assertion for error response data
    const errorMessage = errorData?.detail || errorData?.message || errorData?.error || error?.message || "Request failed";
    
    console.error("[API] Error:", {
      status,
      message: errorMessage,
      url: error?.config?.url,
      data: errorData,
      type: errorData?.type
    });
    
    if (status === 401) {
      localStorage.removeItem("auth_token");
    }
    
    // Show error in console with full details
    if (errorData?.rid) {
      console.error(`[API] Request ID: ${errorData.rid}`);
    }
    
    return Promise.reject(error);
  }
);

export default api;
