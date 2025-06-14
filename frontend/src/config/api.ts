import axios, { AxiosRequestConfig } from 'axios';

// Define the type for Vite's import.meta.env
interface ImportMetaEnv {
  VITE_API_URL: string;
  VITE_CF_ACCESS_CLIENT_ID: string;
  VITE_CF_ACCESS_CLIENT_SECRET: string;
}

declare global {
  interface ImportMeta {
    env: ImportMetaEnv;
  }
}

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const CF_ACCESS_CLIENT_ID = import.meta.env.VITE_CF_ACCESS_CLIENT_ID;
const CF_ACCESS_CLIENT_SECRET = import.meta.env.VITE_CF_ACCESS_CLIENT_SECRET;

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
    'CF-Access-Client-Id': CF_ACCESS_CLIENT_ID,
    'CF-Access-Client-Secret': CF_ACCESS_CLIENT_SECRET,
  },
  withCredentials: true,  // Enable sending cookies and auth headers
});

// Add request interceptor to ensure headers are set for all requests
api.interceptors.request.use((config: AxiosRequestConfig) => {
  // Ensure withCredentials is set for all requests
  config.withCredentials = true;
  
  // Ensure Cloudflare Access headers are set
  if (config.headers) {
    config.headers['CF-Access-Client-Id'] = CF_ACCESS_CLIENT_ID;
    config.headers['CF-Access-Client-Secret'] = CF_ACCESS_CLIENT_SECRET;
  }
  
  return config;
});

export default api; 