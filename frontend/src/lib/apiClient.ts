import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_PREFIX || "/api", // relative by default
  withCredentials: false,
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
