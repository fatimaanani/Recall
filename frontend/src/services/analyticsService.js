import apiClient from "./apiClient";

function toParams({ dateFrom, dateTo, searchBackend }) {
  const params = {};
  if (dateFrom) params.date_from = dateFrom;
  if (dateTo) params.date_to = dateTo;
  if (searchBackend) params.search_backend = searchBackend;
  return params;
}

export function getOperationalAnalytics({ dateFrom, dateTo } = {}) {
  return apiClient
    .get("/api/admin/analytics/overview", { params: toParams({ dateFrom, dateTo }) })
    .then((res) => res.data);
}

export function getEvaluationAnalytics({ dateFrom, dateTo, searchBackend } = {}) {
  return apiClient
    .get("/api/admin/analytics/evaluation", { params: toParams({ dateFrom, dateTo, searchBackend }) })
    .then((res) => res.data);
}

export function listEvaluationTestCases() {
  return apiClient.get("/api/admin/evaluation/test-cases").then((res) => res.data);
}

// Payload keys are already snake_case to match the request body 1:1, no translation happens here.
export function createEvaluationTestCase(payload) {
  return apiClient.post("/api/admin/evaluation/test-cases", payload).then((res) => res.data);
}

export function runEvaluation({ searchBackend = "postgresql", testCaseId = null, resultLimit = 20 } = {}) {
  return apiClient
    .post("/api/admin/evaluation/run", { search_backend: searchBackend, test_case_id: testCaseId, result_limit: resultLimit })
    .then((res) => res.data);
}

export function getElasticsearchHealth() {
  return apiClient.get("/api/admin/elasticsearch/health").then((res) => res.data);
}

export function runElasticsearchBackfill() {
  return apiClient.post("/api/admin/elasticsearch/backfill").then((res) => res.data);
}

// Built as a path (not fetched here) since the endpoint needs the same bearer token as other admin calls; Analytics.jsx fetches it as a blob through apiClient so the Authorization header attaches.
export function exportAnalyticsCsvPath({ dateFrom, dateTo, searchBackend }) {
  const params = new URLSearchParams(toParams({ dateFrom, dateTo, searchBackend })).toString();
  return `/api/admin/analytics/export?${params}`;
}

export function fetchAnalyticsCsvBlob({ dateFrom, dateTo, searchBackend }) {
  return apiClient
    .get(exportAnalyticsCsvPath({ dateFrom, dateTo, searchBackend }), { responseType: "blob" })
    .then((res) => res.data);
}
