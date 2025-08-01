import axios, { AxiosResponse, AxiosError, InternalAxiosRequestConfig } from 'axios';

// Type definitions for API error responses
interface ApiErrorResponse {
  detail?: string;
  message?: string;
  error?: string;
}

// Enhanced error type that includes our custom properties
interface EnhancedError extends Error {
  response?: {
    data?: ApiErrorResponse | string;
    status?: number;
  };
  config?: any;
  isAxiosError?: boolean;
  status?: number;
  serverDetail?: string;
}

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
  (error: AxiosError<ApiErrorResponse | string>) => {
    // Handle Cloudflare Access authentication errors
    if (error.response?.status === 403 && error.response?.headers?.['cf-ray']) {
      console.warn('Cloudflare Access authentication failed');
      // Optionally redirect to Cloudflare Access login or show error message
    }
    
    // Enhanced error logging and processing for better frontend error handling
    const errorInfo = {
      message: error.message,
      status: error.response?.status,
      url: error.config?.url,
      method: error.config?.method?.toUpperCase(),
      serverMessage: typeof error.response?.data === 'object' ? error.response?.data?.detail : undefined,
      fullResponse: error.response?.data,
    };
    
    console.error('API Error:', errorInfo);
    
    // Enhance the error object with better server error details
    if (error.response?.data && typeof error.response.data === 'object' && error.response.data.detail) {
      // Create a new error with the server's detailed message
      const enhancedError = new Error(error.response.data.detail) as EnhancedError;
      // Preserve the original error properties
      Object.assign(enhancedError, {
        response: error.response,
        config: error.config,
        isAxiosError: true,
        status: error.response.status,
        serverDetail: error.response.data.detail,
      });
      return Promise.reject(enhancedError);
    } else if (error.response?.data && typeof error.response.data === 'string') {
      // Handle cases where the error is returned as a plain string
      const enhancedError = new Error(error.response.data) as EnhancedError;
      Object.assign(enhancedError, {
        response: error.response,
        config: error.config,
        isAxiosError: true,
        status: error.response.status,
        serverDetail: error.response.data,
      });
      return Promise.reject(enhancedError);
    } else if (error.response?.status) {
      // Provide meaningful default messages for common HTTP status codes
      let defaultMessage = error.message;
      switch (error.response.status) {
        case 400:
          defaultMessage = 'Bad request. Please check your input and try again.';
          break;
        case 401:
          defaultMessage = 'Unauthorized. Please check your authentication.';
          break;
        case 403:
          defaultMessage = 'Forbidden. You do not have permission to perform this action.';
          break;
        case 404:
          defaultMessage = 'Resource not found.';
          break;
        case 500:
          defaultMessage = 'Internal server error. Please try again later.';
          break;
        case 502:
          defaultMessage = 'Bad gateway. The server is temporarily unavailable.';
          break;
        case 503:
          defaultMessage = 'Service unavailable. Please try again later.';
          break;
        case 504:
          defaultMessage = 'Gateway timeout. The request took too long to process.';
          break;
      }
      
      const enhancedError = new Error(defaultMessage) as EnhancedError;
      Object.assign(enhancedError, {
        response: error.response,
        config: error.config,
        isAxiosError: true,
        status: error.response.status,
        serverDetail: defaultMessage,
      });
      return Promise.reject(enhancedError);
    }
    
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

// Utility function to extract meaningful error messages from API errors
export const extractErrorMessage = (error: any, defaultMessage: string = 'An unexpected error occurred'): string => {
  // Check if it's our enhanced axios error with serverDetail
  if (error && typeof error === 'object' && 'serverDetail' in error && error.serverDetail) {
    return error.serverDetail;
  }
  
  // Check for standard axios error response structure
  if (error?.response?.data && typeof error.response.data === 'object' && 'detail' in error.response.data && error.response.data.detail) {
    return error.response.data.detail;
  }
  
  // Check for string response data
  if (error?.response?.data && typeof error.response.data === 'string') {
    return error.response.data;
  }
  
  // Check for other common error structures
  if (error?.response?.data && typeof error.response.data === 'object') {
    if ('message' in error.response.data && error.response.data.message) {
      return error.response.data.message;
    }
    
    if ('error' in error.response.data && error.response.data.error) {
      return error.response.data.error;
    }
  }
  
  // Fall back to error message
  if (error?.message) {
    return error.message;
  }
  
  // Last resort
  return defaultMessage;
};

export default api; 