import axios, { AxiosError, InternalAxiosRequestConfig, AxiosResponse } from "axios";

const getBaseURL = () => {
  // NEVER use Fly.dev or devinapps.com - we use Railway backend via Cloudflare proxy
  // Only check environment variables, otherwise use /api (Cloudflare Pages proxy)
  
  if (import.meta.env.VITE_API_BASE_URL) {
    console.warn('[API] VITE_API_BASE_URL is set:', import.meta.env.VITE_API_BASE_URL);
    console.warn('[API] This will bypass Cloudflare proxy! Consider removing this variable.');
    return import.meta.env.VITE_API_BASE_URL;
  }
  
  if (import.meta.env.VITE_API_URL) {
    console.warn('[API] VITE_API_URL is set:', import.meta.env.VITE_API_URL);
    console.warn('[API] This will bypass Cloudflare proxy! Consider removing this variable.');
    return import.meta.env.VITE_API_URL;
  }
  
  if (import.meta.env.VITE_API_PREFIX) {
    console.warn('[API] VITE_API_PREFIX is set:', import.meta.env.VITE_API_PREFIX);
    return import.meta.env.VITE_API_PREFIX;
  }
  
  // Default: use /api which routes through Cloudflare Pages Function proxy to Railway
  console.log('[API] Using /api (Cloudflare proxy -> Railway backend)');
  return "/api";
};

const api = axios.create({
  baseURL: getBaseURL(),
  withCredentials: false,
  timeout: 15000,
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
