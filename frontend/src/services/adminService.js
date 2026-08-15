import apiClient from "./apiClient";

export function listUsers() {
  return apiClient.get("/api/admin/users").then((res) => res.data);
}

export function suspendUser(userId) {
  return apiClient.patch(`/api/admin/users/${userId}/suspend`).then((res) => res.data);
}

export function reactivateUser(userId) {
  return apiClient.patch(`/api/admin/users/${userId}/reactivate`).then((res) => res.data);
}

// Requires typed username confirmation
export function deleteUser(userId, username) {
  return apiClient
    .delete(`/api/admin/users/${userId}`, { data: { username } })
    .then((res) => res.data);
}

// Used by Add Administrator's "Check Account" step
export function lookupUserByEmail(email) {
  return apiClient.post("/api/admin/users/lookup-by-email", { email }).then((res) => res.data);
}

export function promoteToAdmin(email) {
  return apiClient.post("/api/admin/promote-to-admin", { email }).then((res) => res.data);
}

export function listUploads() {
  return apiClient.get("/api/admin/uploads").then((res) => res.data);
}

export function getUserUploads(userId) {
  return apiClient.get(`/api/admin/users/${userId}/uploads`).then((res) => res.data);
}

export function getUploadDetail(videoId) {
  return apiClient.get(`/api/admin/uploads/${videoId}`).then((res) => res.data);
}

// Pass to useProtectedImage
export function getUploadThumbnailPath(videoId) {
  return `/api/admin/uploads/${videoId}/thumbnail`;
}

export function deleteUpload(videoId) {
  return apiClient.delete(`/api/admin/uploads/${videoId}`).then((res) => res.data);
}

export function listMessageAdministrators() {
  return apiClient.get("/api/admin/messages/administrators").then((res) => res.data);
}

export function listReceivedMessages() {
  return apiClient.get("/api/admin/messages/received").then((res) => res.data);
}

export function sendAdminMessage(recipientAdminId, message) {
  return apiClient
    .post("/api/admin/messages", { recipient_admin_id: recipientAdminId, message })
    .then((res) => res.data);
}
