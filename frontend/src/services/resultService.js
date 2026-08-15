import apiClient from "./apiClient";

// Reads the SearchResult's full context (query, scores, categories, clip info, saved state) from the result id alone, so Scene Viewer doesn't depend on React Router location.state for correctness on refresh/direct navigation.
// Optional AbortController signal, same reasoning as clipService.generateClip.
export function getResult(resultId, { signal } = {}) {
  return apiClient.get(`/api/results/${resultId}`, { signal }).then((res) => res.data);
}

// Only succeeds if a GeneratedClip already exists for it (enforced backend-side).
export function saveResult(resultId) {
  return apiClient.post(`/api/results/${resultId}/save`).then((res) => res.data);
}

// Idempotent, safe to call even if already unsaved.
export function unsaveResult(resultId) {
  return apiClient.delete(`/api/results/${resultId}/save`).then((res) => res.data);
}

export function getSaveStatus(resultId) {
  return apiClient.get(`/api/results/${resultId}/save-status`).then((res) => res.data);
}
