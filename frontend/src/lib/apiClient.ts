import axios, { AxiosError, InternalAxiosRequestConfig, AxiosResponse } from "axios";

const getBaseURL = () => {
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL;
  }
  
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  
  if (import.meta.env.VITE_API_PREFIX) {
    return import.meta.env.VITE_API_PREFIX;
  }
  
  if (typeof window !== 'undefined' && window.location.hostname.includes('devinapps.com')) {
    return 'https://app-vatxxrtj.fly.dev';
  }
  
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
    const errorData = error?.response?.data;
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
