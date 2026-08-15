import apiClient from "./apiClient";

// Resolves scene boundaries and generates/reuses the clip. Returns clip_stream_url as-is (server-computed, never reconstructed here) for useProtectedMedia.
// Optional AbortController signal, Scene Viewer passes one so a StrictMode-double-invoked mount effect's stale request can be cancelled.
export function generateClip(resultId, { signal } = {}) {
  return apiClient.post(`/api/results/${resultId}/clip`, undefined, { signal }).then((res) => res.data);
}
