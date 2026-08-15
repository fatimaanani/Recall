import axios from "axios";

// Access token, sessionStorage (per-tab, not shared across tabs like localStorage)
export const ACCESS_TOKEN_STORAGE_KEY = "sceneFinderAccessToken";

// One-time cleanup, stale token from pre-sessionStorage days
localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
});

// Attach bearer token to every request
apiClient.interceptors.request.use((config) => {
  const token = sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Clear token on 401, AuthContext handles the redirect
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      sessionStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
    }
    return Promise.reject(error);
  }
);

// Error message extraction, handles both plain-string and Pydantic 422 array details
export function getErrorMessage(error, fallback = "Something went wrong. Please try again.") {
  const detail = error?.response?.data?.detail;

  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        // Drop leading "body"/"query"/"path" from Pydantic's loc
        const field = Array.isArray(item?.loc) ? item.loc.slice(1).join(".") : null;
        const msg = item?.msg ?? "Invalid value.";
        return field ? `${field}: ${msg}` : msg;
      })
      .join(" ");
  }

  return fallback;
}

export default apiClient;
