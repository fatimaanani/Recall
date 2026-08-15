// A temporary, tab-scoped copy of the latest search results plus Results' page/filter/sort state, kept in sessionStorage so it survives navigating to Scene Viewer and back and a refresh on Results, without becoming permanent data.
// Deliberately sessionStorage, not localStorage: it's per-tab and clears when the tab closes, and logout explicitly clears it too (see AuthContext.jsx) so it never leaks into the next login on the same tab.
// This module never touches saved_results in Postgres, that's handled separately by resultService.js.

const STORAGE_KEY = "recall.currentSearchSession";

// Bumped when the stored session's shape changes; a session written under a different version is discarded rather than misinterpreted.
const SESSION_VERSION = 1;

export const DEFAULT_TYPE_FILTER = null;
export const DEFAULT_SORT_BY = "best_match";
export const DEFAULT_PAGE = 1;

// Returns null if no session exists, it's corrupt, or it was written under a different SESSION_VERSION, rather than throwing.
export function loadSearchSession() {
  let raw;
  try {
    raw = sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null; // sessionStorage unavailable (e.g. private-mode edge cases)
  }
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || !parsed.searchResponse) return null;
    if (parsed.version !== SESSION_VERSION) return null;
    return parsed;
  } catch {
    return null;
  }
}

// Called by Home.jsx/Search.jsx after a successful search; replaces any previous session and always starts at page 1 with default filters/sort.
export function startSearchSession({ searchResponse, queryLabel }) {
  const session = {
    version: SESSION_VERSION,
    searchResponse,
    queryLabel,
    page: DEFAULT_PAGE,
    typeFilter: DEFAULT_TYPE_FILTER,
    sortBy: DEFAULT_SORT_BY,
    savedAt: new Date().toISOString(),
  };
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // sessionStorage full/unavailable: this navigation still works from route state, it just won't survive a refresh.
  }
  return session;
}

export function updateSearchSession(patch) {
  const current = loadSearchSession();
  if (!current) return;
  const next = { ...current, ...patch };
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    
  }
}

export function clearSearchSession() {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    
  }
}


export function resolveInitialResultsState({ routeSearchResponse, routeQueryLabel }) {
  if (routeSearchResponse) {
    startSearchSession({ searchResponse: routeSearchResponse, queryLabel: routeQueryLabel });
    return {
      searchResponse: routeSearchResponse,
      queryLabel: routeQueryLabel,
      page: DEFAULT_PAGE,
      typeFilter: DEFAULT_TYPE_FILTER,
      sortBy: DEFAULT_SORT_BY,
    };
  }

  const restored = loadSearchSession();
  if (!restored) return null;
  return {
    searchResponse: restored.searchResponse,
    queryLabel: restored.queryLabel,
    page: restored.page ?? DEFAULT_PAGE,
    typeFilter: restored.typeFilter ?? DEFAULT_TYPE_FILTER,
    sortBy: restored.sortBy ?? DEFAULT_SORT_BY,
  };
}
