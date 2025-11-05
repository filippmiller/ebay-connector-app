import axios from "axios";

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

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("auth_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      localStorage.removeItem("auth_token");
    }
    return Promise.reject(error);
  }
);

export default api;
