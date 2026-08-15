import apiClient from "./apiClient";

export function createCategory(name) {
  return apiClient.post("/api/categories", { name }).then((res) => res.data);
}

export function listCategories() {
  return apiClient.get("/api/categories").then((res) => res.data);
}

// Used by the collection-detail page
export function getCategoryDetail(categoryId) {
  return apiClient.get(`/api/categories/${categoryId}`).then((res) => res.data);
}

export function renameCategory(categoryId, name) {
  return apiClient.patch(`/api/categories/${categoryId}`, { name }).then((res) => res.data);
}

export function deleteCategory(categoryId) {
  return apiClient.delete(`/api/categories/${categoryId}`).then((res) => res.data);
}

export function addVideoToCategory(categoryId, videoId) {
  return apiClient.post(`/api/categories/${categoryId}/videos/${videoId}`).then((res) => res.data);
}

export function removeVideoFromCategory(categoryId, videoId) {
  return apiClient
    .delete(`/api/categories/${categoryId}/videos/${videoId}`)
    .then((res) => res.data);
}
