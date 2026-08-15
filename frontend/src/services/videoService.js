import apiClient from "./apiClient";

// Upload, no explicit Content-Type, browser sets multipart boundary itself
export function uploadVideo(formData, onUploadProgress) {
  return apiClient.post("/api/videos", formData, { onUploadProgress }).then((res) => res.data);
}

export function listVideos() {
  return apiClient.get("/api/videos").then((res) => res.data);
}

export function getVideo(videoId) {
  return apiClient.get(`/api/videos/${videoId}`).then((res) => res.data);
}

// Thumbnail path, pass to useProtectedImage, not a direct <img src>
export function getThumbnailPath(videoId) {
  return `/api/videos/${videoId}/thumbnail`;
}

// Same pattern as getThumbnailPath, a path string only, never fetched directly here.
export function getStreamPath(videoId) {
  return `/api/videos/${videoId}/stream`;
}

// Transcript, read-only, ordered by start_time
export function getTranscript(videoId) {
  return apiClient.get(`/api/videos/${videoId}/transcript`).then((res) => res.data);
}

// Current user's bookmarks only, newest saved first. Used by Upload Details' Saved Scenes panel.
export function listSavedForVideo(videoId) {
  return apiClient.get(`/api/videos/${videoId}/saved-results`).then((res) => res.data);
}

export function renameVideo(videoId, title) {
  return apiClient.patch(`/api/videos/${videoId}`, { title }).then((res) => res.data);
}

export function deleteVideo(videoId) {
  return apiClient.delete(`/api/videos/${videoId}`).then((res) => res.data);
}

// Reprocess, retry a failed video
export function reprocessVideo(videoId) {
  return apiClient.post(`/api/videos/${videoId}/reprocess`).then((res) => res.data);
}
