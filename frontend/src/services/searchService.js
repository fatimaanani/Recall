import apiClient from "./apiClient";

// query_type is "exact_text" | "semantic" (speech_to_text is rejected on this route, use searchSpeech instead).
export function searchText({ query_text, query_type, search_scope, limit }) {
  return apiClient
    .post("/api/search", { query_text, query_type, search_scope, limit })
    .then((res) => res.data);
}

// audioFile is a File object (MP3/WAV/FLAC/M4A); the backend re-validates extension + magic bytes regardless of any client-side check.
export function searchSpeech({ audioFile, search_scope, limit }) {
  const formData = new FormData();
  formData.append("audio", audioFile);
  formData.append("search_scope", search_scope);
  if (limit != null) formData.append("limit", limit);
  return apiClient.post("/api/search/speech", formData).then((res) => res.data);
}

// Newest-first list of the current user's own past searches; the backend doesn't support offset/page params.
export function listHistory(limit) {
  return apiClient.get("/api/search/history", { params: { limit } }).then((res) => res.data);
}
