// verify-frontend-logic.mjs
//
// Zero-dependency Node script (no jest/vitest/mocha -- deliberately not a
// test framework, per this project's "don't introduce a frontend test
// framework without approval" rule) that exercises pure, framework-free
// frontend logic directly with Node's built-in assert module.
//
// Run: node scripts/verify-frontend-logic.mjs
//
// 1. sessionStorage stub (searchSession.js expects the browser global)
// 2. Checks -- searchSession.js: session round-trip, version rejection,
//    resolveInitialResultsState (fresh search / restore / no session)
// 3. Checks -- save/unsave never touch the search session (source-scan,
//    since resultService.js/apiClient.js import.meta.env isn't
//    resolvable outside a Vite build, so they can't be imported directly
//    from plain Node)
// 4. Report + exit code

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_DIR = path.join(__dirname, "..", "src");

// 1. sessionStorage stub
class FakeStorage {
  constructor() {
    this._data = new Map();
  }
  getItem(key) {
    return this._data.has(key) ? this._data.get(key) : null;
  }
  setItem(key, value) {
    this._data.set(key, String(value));
  }
  removeItem(key) {
    this._data.delete(key);
  }
  clear() {
    this._data.clear();
  }
}
globalThis.sessionStorage = new FakeStorage();

const results = [];
function check(name, fn) {
  try {
    fn();
    results.push({ name, ok: true });
  } catch (err) {
    results.push({ name, ok: false, err });
  }
}

// Dynamic import() requires a real file:// URL on Windows -- a raw
// absolute path string like "C:\...\searchSession.js" makes Node parse
// "C:" as a URL protocol and throw ERR_UNSUPPORTED_ESM_URL_SCHEME.
// pathToFileURL() does the platform-correct conversion (no-op on POSIX,
// where a raw absolute path already happens to work, which is why this
// went unnoticed until it was actually run on Windows).
const searchSession = await import(pathToFileURL(path.join(SRC_DIR, "utils", "searchSession.js")));
const {
  startSearchSession,
  loadSearchSession,
  updateSearchSession,
  clearSearchSession,
  resolveInitialResultsState,
  DEFAULT_PAGE,
  DEFAULT_TYPE_FILTER,
  DEFAULT_SORT_BY,
} = searchSession;

function fakeSearchResponse(overrides = {}) {
  return {
    search_query_id: 1,
    query_text: "binary search tree",
    query_type: "exact_text",
    search_scope: "both",
    response_time_ms: 12.3,
    result_count: 3,
    results: [
      { result_id: 1, video_id: 1 },
      { result_id: 2, video_id: 2 },
      { result_id: 3, video_id: 3 },
    ],
    transcribed_text: null,
    ...overrides,
  };
}

// 2. searchSession.js checks

check("startSearchSession + loadSearchSession round-trip", () => {
  sessionStorage.clear();
  const response = fakeSearchResponse();
  startSearchSession({ searchResponse: response, queryLabel: "binary search tree" });
  const loaded = loadSearchSession();
  assert.ok(loaded, "expected a session to be loaded");
  assert.deepEqual(loaded.searchResponse, response);
  assert.equal(loaded.queryLabel, "binary search tree");
  assert.equal(loaded.page, DEFAULT_PAGE);
  assert.equal(loaded.typeFilter, DEFAULT_TYPE_FILTER);
  assert.equal(loaded.sortBy, DEFAULT_SORT_BY);
});

check("updateSearchSession merges page/filter/sort without touching searchResponse", () => {
  sessionStorage.clear();
  const response = fakeSearchResponse();
  startSearchSession({ searchResponse: response, queryLabel: "binary search tree" });
  updateSearchSession({ page: 2, typeFilter: "video", sortBy: "newest" });
  const loaded = loadSearchSession();
  assert.equal(loaded.page, 2);
  assert.equal(loaded.typeFilter, "video");
  assert.equal(loaded.sortBy, "newest");
  // The result list itself -- unsaved sibling results -- must be
  // byte-for-byte unchanged by a page/filter/sort update.
  assert.deepEqual(loaded.searchResponse.results, response.results);
});

check("updateSearchSession is a no-op when there is no current session", () => {
  sessionStorage.clear();
  updateSearchSession({ page: 5 });
  assert.equal(loadSearchSession(), null);
});

check("loadSearchSession rejects a version mismatch instead of guessing", () => {
  sessionStorage.clear();
  sessionStorage.setItem(
    "recall.currentSearchSession",
    JSON.stringify({ version: 0, searchResponse: fakeSearchResponse() })
  );
  assert.equal(loadSearchSession(), null);
});

check("clearSearchSession removes the session (logout contract)", () => {
  sessionStorage.clear();
  startSearchSession({ searchResponse: fakeSearchResponse(), queryLabel: "x" });
  assert.ok(loadSearchSession());
  clearSearchSession();
  assert.equal(loadSearchSession(), null);
});

check("resolveInitialResultsState: real route state always wins and resets page/filter/sort", () => {
  sessionStorage.clear();
  // Simulate an existing session with a non-default page/filter/sort,
  // as if the user had already been browsing Results before this
  // fresh search replaced it.
  startSearchSession({ searchResponse: fakeSearchResponse({ result_count: 1 }), queryLabel: "old query" });
  updateSearchSession({ page: 3, typeFilter: "audio", sortBy: "oldest" });

  const freshResponse = fakeSearchResponse({ query_text: "new query" });
  const state = resolveInitialResultsState({ routeSearchResponse: freshResponse, routeQueryLabel: "new query" });

  assert.deepEqual(state.searchResponse, freshResponse);
  assert.equal(state.queryLabel, "new query");
  assert.equal(state.page, DEFAULT_PAGE);
  assert.equal(state.typeFilter, DEFAULT_TYPE_FILTER);
  assert.equal(state.sortBy, DEFAULT_SORT_BY);

  // And it must have actually replaced the stored session, not just the
  // return value.
  const stored = loadSearchSession();
  assert.deepEqual(stored.searchResponse, freshResponse);
  assert.equal(stored.page, DEFAULT_PAGE);
});

check("resolveInitialResultsState: no route state restores the existing session as-is", () => {
  sessionStorage.clear();
  const response = fakeSearchResponse();
  startSearchSession({ searchResponse: response, queryLabel: "restored query" });
  updateSearchSession({ page: 2, typeFilter: "video", sortBy: "newest" });

  const state = resolveInitialResultsState({ routeSearchResponse: null, routeQueryLabel: null });

  assert.deepEqual(state.searchResponse, response);
  assert.equal(state.queryLabel, "restored query");
  assert.equal(state.page, 2);
  assert.equal(state.typeFilter, "video");
  assert.equal(state.sortBy, "newest");
});

check("resolveInitialResultsState: no route state and no session is honestly null", () => {
  sessionStorage.clear();
  const state = resolveInitialResultsState({ routeSearchResponse: null, routeQueryLabel: null });
  assert.equal(state, null);
});

check("resolveInitialResultsState: a session started by one 'search' survives an unrelated page/filter/sort update, simulating a Scene Viewer round trip with no save", () => {
  sessionStorage.clear();
  const response = fakeSearchResponse();
  startSearchSession({ searchResponse: response, queryLabel: "q" });
  // Simulate navigating to Scene Viewer and back with no interaction --
  // Results.jsx's sync effect still fires once on mount with the
  // restored page/filter/sort, which should be a pure no-op here.
  const first = resolveInitialResultsState({ routeSearchResponse: null, routeQueryLabel: null });
  updateSearchSession({ page: first.page, typeFilter: first.typeFilter, sortBy: first.sortBy });
  const second = resolveInitialResultsState({ routeSearchResponse: null, routeQueryLabel: null });
  assert.deepEqual(second.searchResponse, response);
  assert.equal(second.searchResponse.results.length, 3);
});

// 3. Source-scan: save/unsave must never reach the search session.
// resultService.js/apiClient.js can't be imported directly here (they
// reference import.meta.env, which only resolves inside a Vite build),
// so this is a text-level regression guard instead of an executed call --
// it still fails loudly if a future change ever wires saveResult/
// unsaveResult (or anything else in resultService.js) into
// sessionStorage or searchSession.js.
check("resultService.js source never references sessionStorage or searchSession", () => {
  const source = readFileSync(path.join(SRC_DIR, "services", "resultService.js"), "utf8");
  assert.ok(!/sessionStorage/.test(source), "resultService.js must not touch sessionStorage directly");
  assert.ok(!/searchSession/.test(source), "resultService.js must not import searchSession.js");
});

check("SceneViewer.jsx's handleToggleBookmark never navigates or touches the search session", () => {
  const source = readFileSync(path.join(SRC_DIR, "pages", "SceneViewer.jsx"), "utf8");
  const match = source.match(/function handleToggleBookmark\(\)\s*{[\s\S]*?\n  }/);
  assert.ok(match, "expected to find handleToggleBookmark in SceneViewer.jsx");
  const body = match[0];
  assert.ok(!/sessionStorage/.test(body), "handleToggleBookmark must not touch sessionStorage");
  assert.ok(!/searchSession/.test(body), "handleToggleBookmark must not touch searchSession.js");
  assert.ok(!/navigate\(/.test(body), "handleToggleBookmark must not navigate");
});

// 4. Report

let failed = 0;
for (const r of results) {
  if (r.ok) {
    console.log(`PASS  ${r.name}`);
  } else {
    failed += 1;
    console.log(`FAIL  ${r.name}`);
    console.log(`      ${r.err.message}`);
  }
}
console.log(`\n${results.length - failed}/${results.length} checks passed.`);
process.exit(failed > 0 ? 1 : 0);
