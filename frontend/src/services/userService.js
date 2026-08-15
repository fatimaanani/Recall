import apiClient from "./apiClient";

export function getStorageUsage() {
  return apiClient.get("/api/users/me/storage").then((res) => res.data);
}

export function updateProfile(payload) {
  return apiClient.patch("/api/users/me/profile", payload).then((res) => res.data);
}

export function changePassword(currentPassword, newPassword) {
  return apiClient
    .patch("/api/users/me/password", {
      current_password: currentPassword,
      new_password: newPassword,
    })
    .then((res) => res.data);
}

export function deleteAccount(password) {
  return apiClient
    .delete("/api/users/me", { data: { password } })
    .then((res) => res.data);
}
