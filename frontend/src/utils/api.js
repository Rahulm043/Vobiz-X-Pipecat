import { supabase } from '../supabaseClient';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:7860';

/**
 * Authenticated fetch wrapper for backend API calls.
 */
export async function authFetch(endpoint, options = {}) {
    const { data: { session } } = await supabase.auth.getSession();
    const token = session?.access_token;

    const headers = {
        'Content-Type': 'application/json',
        'ngrok-skip-browser-warning': 'true',
        ...options.headers,
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const url = endpoint.startsWith('http') ? endpoint : `${API_BASE}${endpoint}`;
    console.log(`[authFetch] ${options.method || 'GET'} ${url} | Token exists: ${!!token}`);
    // console.log(`[authFetch] ${options.method || 'GET'} ${url}`);
    
    const response = await fetch(url, {
        cache: 'no-store',
        ...options,
        headers,
    });

    if (response.status === 401) {
        console.warn(`[authFetch] 401 Unauthorized for ${url}. Token valid: ${!!token}`);
    }

    return response;
}

/**
 * Fetcher for SWR hooks
 */
export const swrFetcher = async (endpoint) => {
    const res = await authFetch(endpoint);
    if (!res.ok) {
        const error = new Error('An error occurred while fetching the data.');
        error.info = await res.json().catch(() => ({}));
        error.status = res.status;
        throw error;
    }
    return res.json();
};
