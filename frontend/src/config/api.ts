import axios, { AxiosResponse, AxiosError, InternalAxiosRequestConfig } from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Cloudflare service auth configuration
const CF_CLIENT_ID = import.meta.env.VITE_CF_CLIENT_ID;
const CF_CLIENT_SECRET = import.meta.env.VITE_CF_CLIENT_SECRET;
const CF_ACCESS_TOKEN = import.meta.env.VITE_CF_ACCESS_TOKEN;

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    // Add Cloudflare Access headers if available
    ...(CF_CLIENT_ID && { 'CF-Access-Client-Id': CF_CLIENT_ID }),
    ...(CF_CLIENT_SECRET && { 'CF-Access-Client-Secret': CF_CLIENT_SECRET }),
    ...(CF_ACCESS_TOKEN && { 'CF-Access-Token': CF_ACCESS_TOKEN }),
  },
  withCredentials: true, // Include cookies for Cloudflare Access
});

// Request interceptor to add dynamic headers
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // Add any dynamic headers here
    const token = localStorage.getItem('cf_access_token');
    if (token && config.headers) {
      config.headers['CF-Access-Token'] = token;
    }

    // Add CSRF token if available
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    if (csrfToken && config.headers) {
      config.headers['X-CSRF-Token'] = csrfToken;
    }

    return config;
  },
  (error: AxiosError) => {
    return Promise.reject(error);
  }
);

// Response interceptor to handle Cloudflare Access errors
api.interceptors.response.use(
  (response: AxiosResponse) => {
    return response;
  },
  (error: AxiosError) => {
    // Handle Cloudflare Access authentication errors
    if (error.response?.status === 403 && error.response?.headers?.['cf-ray']) {
      console.warn('Cloudflare Access authentication failed');
      // Optionally redirect to Cloudflare Access login
      // window.location.href = '/cdn-cgi/access/login';
    }
    
    // Handle CORS errors
    if (error.message?.includes('CORS')) {
      console.error('CORS error detected:', error.message);
    }
    
    return Promise.reject(error);
  }
);

export default api; 