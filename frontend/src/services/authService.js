import apiClient from "./apiClient";

export function register(payload) {
  return apiClient.post("/api/auth/register", payload).then((res) => res.data);
}

export function login(payload) {
  return apiClient.post("/api/auth/login", payload).then((res) => res.data);
}

export function getCurrentUser() {
  return apiClient.get("/api/auth/me").then((res) => res.data);
}

// Backend always responds the same way regardless of whether the email matches an account, no enumeration.
export function forgotPassword(email) {
  return apiClient.post("/api/auth/forgot-password", { email }).then((res) => res.data);
}

export function resetPassword(token, newPassword) {
  return apiClient
    .post("/api/auth/reset-password", { token, new_password: newPassword })
    .then((res) => res.data);
}
