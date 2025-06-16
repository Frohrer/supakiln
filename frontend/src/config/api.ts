import axios, { AxiosResponse, AxiosError, InternalAxiosRequestConfig } from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Cloudflare service auth configuration
const CF_CLIENT_ID = import.meta.env.VITE_CF_CLIENT_ID;
const CF_CLIENT_SECRET = import.meta.env.VITE_CF_CLIENT_SECRET;
const CF_ACCESS_TOKEN = import.meta.env.VITE_CF_ACCESS_TOKEN;

// Create axios instance with Cloudflare Access configuration
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
  timeout: 30000, // 30 second timeout
});



// Enhanced request interceptor
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // Add dynamic headers
    const token = localStorage.getItem('cf_access_token');
    if (token && config.headers) {
      config.headers['CF-Access-Token'] = token;
    }

    // Add CSRF token if available
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    if (csrfToken && config.headers) {
      config.headers['X-CSRF-Token'] = csrfToken;
    }

    // Log request for debugging
    console.log(`Making ${config.method?.toUpperCase()} request to ${config.url}`, {
      headers: config.headers,
      hasCloudflareAuth: !!(CF_CLIENT_ID && CF_CLIENT_SECRET),
    });

    return config;
  },
  (error: AxiosError) => {
    console.error('Request interceptor error:', error);
    return Promise.reject(error);
  }
);

// Simplified response interceptor for Cloudflare Access
api.interceptors.response.use(
  (response: AxiosResponse) => {
    return response;
  },
  (error: AxiosError) => {
    // Handle Cloudflare Access authentication errors
    if (error.response?.status === 403 && error.response?.headers?.['cf-ray']) {
      console.warn('Cloudflare Access authentication failed');
      // Optionally redirect to Cloudflare Access login or show error message
    }
    
    // Log errors for debugging
    console.error('API Error:', {
      message: error.message,
      status: error.response?.status,
      url: error.config?.url,
    });
    
    return Promise.reject(error);
  }
);

// Export a function to test the API connection
export const testApiConnection = async () => {
  try {
    const response = await api.get('/health');
    console.log('API connection test successful:', response.data);
    return true;
  } catch (error) {
    console.error('API connection test failed:', error);
    return false;
  }
};

// Export a simplified function to make authenticated requests
export const makeAuthenticatedRequest = async (
  url: string, 
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' = 'GET', 
  data?: any
) => {
  const response = await api.request({
    url,
    method: method.toLowerCase(),
    ...(data && { data }),
  });
  return response.data;
};

export default api; 