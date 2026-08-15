import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import "../styles/pages/Results.css";

import Icon from "../components/Icon";
import AssetPlaceholder from "../components/AssetPlaceholder";
import Pagination from "../components/Pagination";
import { MethodBadge } from "../components/Badge";
import { useProtectedImage } from "../hooks/useProtectedImage";
import * as videoService from "../services/videoService";
import {
  updateSearchSession,
  resolveInitialResultsState,
  DEFAULT_PAGE,
  DEFAULT_TYPE_FILTER,
  DEFAULT_SORT_BY,
} from "../utils/searchSession";
import greenLeafImg from "../assets/decorations/greenLeaf-trimmed.png";

const TYPE_FILTERS = [
  { id: "video", label: "Video", icon: "film" },
  { id: "audio", label: "Audio", icon: "music" },
  { id: "other", label: "Others", icon: "file-text" },
];

const SORT_OPTIONS = [
  { id: "best_match", label: "Best Match" },
  { id: "newest", label: "Latest Added" },
  { id: "oldest", label: "Oldest Added" },
  { id: "smallest", label: "Smallest" },
  { id: "largest", label: "Largest" },
];

// rank_position is the backend's own authoritative confidence ordering.
const SORT_COMPARATORS = {
  best_match: (a, b) => a.rank_position - b.rank_position,
  newest: (a, b) => new Date(b.video_uploaded_at) - new Date(a.video_uploaded_at),
  oldest: (a, b) => new Date(a.video_uploaded_at) - new Date(b.video_uploaded_at),
  smallest: (a, b) => a.video_file_size_bytes - b.video_file_size_bytes,
  largest: (a, b) => b.video_file_size_bytes - a.video_file_size_bytes,
};

const PAGE_SIZE = 6;

function formatSeconds(seconds) {
  if (seconds == null) return null;
  const total = Math.round(seconds);
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

function formatTimeRange(start, end) {
  const startLabel = formatSeconds(start);
  const endLabel = formatSeconds(end);
  if (startLabel == null && endLabel == null) return null;
  if (startLabel != null && endLabel != null) return `${startLabel} - ${endLabel}`;
  return startLabel ?? endLabel;
}

// A dedicated component so the useProtectedImage hook is called at most once per card, not inside the page's .map().
function ResultCard({ result, searchMethod }) {
  const hasVisualThumbnail = result.media_type !== "audio";
  const thumbnailUrl = useProtectedImage(
    hasVisualThumbnail && result.has_thumbnail ? videoService.getThumbnailPath(result.video_id) : null
  );

  const subtitle = formatTimeRange(result.matched_start_time, result.matched_end_time);
  const secondaryLabel = result.categories.length > 0 ? result.categories.map((c) => c.name).join(", ") : "Uncategorized";

  return (
    <article className="result-card">
      <div className="card-top">
        <MethodBadge method={searchMethod} />
        <strong>{Math.round(result.confidence_score * 100)}% Match</strong>
      </div>
      {hasVisualThumbnail && (
        thumbnailUrl ? (
          <img src={thumbnailUrl} alt="" style={{ borderRadius: "var(--radius-sm)", width: "100%", height: 110, objectFit: "cover", display: "block" }} />
        ) : (
          <AssetPlaceholder path={`assets/thumbnails/${result.video_id}.png`} width="100%" height={110} className="media-card__thumb" />
        )
      )}
      <p className="card-title">{result.video_title}</p>
      {subtitle && <p className="card-meta">{subtitle}</p>}
      <p className="card-meta">
        <Icon name="folder" size={12} /> {secondaryLabel}
      </p>
      <div className="card-actions">
        {/* fromResults tells Scene Viewer whether "Back to Results" makes sense versus "Go to Search" for a direct/bookmarked visit. */}
        <Link
          to={`/scene-viewer/${result.result_id}`}
          className="btn btn--primary btn--block card-view-scene-btn"
          state={{ fromResults: true }}
        >
          View Scene
        </Link>
      </div>
    </article>
  );
}

export default function Results() {
  const location = useLocation();
  const routeSearchResponse = location.state?.searchResponse ?? null;
  const routeQueryLabel = location.state?.queryLabel ?? null;

  // Computed once via the useState initializer so a later sessionStorage write doesn't change what this page thinks it loaded with; the decision logic itself lives in resolveInitialResultsState (searchSession.js).
  const [initial] = useState(() => resolveInitialResultsState({ routeSearchResponse, routeQueryLabel }));

  const searchResponse = initial?.searchResponse ?? null;
  const queryLabel = initial?.queryLabel ?? null;

  const [typeFilter, setTypeFilter] = useState(initial?.typeFilter ?? DEFAULT_TYPE_FILTER);
  const [sortBy, setSortBy] = useState(initial?.sortBy ?? DEFAULT_SORT_BY);
  const [currentPage, setCurrentPage] = useState(initial?.page ?? DEFAULT_PAGE);

  // Keeps the current search session's page/filter/sort in sync so Scene Viewer and back (or a refresh) restore exactly what the user had.
  useEffect(() => {
    if (!searchResponse) return;
    updateSearchSession({ page: currentPage, typeFilter, sortBy });
  }, [searchResponse, currentPage, typeFilter, sortBy]);

  // No route state and no restorable session, most likely a hard refresh with no prior search this browser session.
  if (!searchResponse) {
    return (
      <div style={{ textAlign: "center", padding: "64px 16px" }}>
        <p style={{ fontWeight: 500, fontFamily: "var(--font-extended)", fontSize: 16 }}>
          We couldn't find these search results.
        </p>
        <p className="text-muted">
          Start a new search to see results here.
        </p>
        <Link to="/search" className="btn btn--primary" style={{ display: "inline-flex", marginTop: 12 }}>
          <Icon name="search" size={16} />
          <span>Go to Search</span>
        </Link>
      </div>
    );
  }

  function handleTypeFilterToggle(id) {
    setTypeFilter((current) => (current === id ? null : id));
    setCurrentPage(1);
  }

  function handleSortChange(value) {
    setSortBy(value);
    setCurrentPage(1);
  }

  const filteredResults = searchResponse.results
    .filter((r) => typeFilter === null || r.media_type === typeFilter)
    .slice()
    .sort(SORT_COMPARATORS[sortBy]);

  const totalPages = Math.max(1, Math.ceil(filteredResults.length / PAGE_SIZE));
  const safePage = Math.min(currentPage, totalPages);
  const pageStart = (safePage - 1) * PAGE_SIZE;
  const pagedResults = filteredResults.slice(pageStart, pageStart + PAGE_SIZE);

  return (
    <div>
      <div className="meta-bar">
        <div className="meta-item">
          <span className="meta-item-label">{searchResponse.query_type === "speech_to_text" ? "Audio Input" : "Search Query"}</span>
          <span className="meta-item-value">{queryLabel}</span>
        </div>
        {searchResponse.query_type === "speech_to_text" && searchResponse.transcribed_text && (
          <div className="meta-item">
            <span className="meta-item-label">We Heard</span>
            <span className="meta-item-value">{searchResponse.transcribed_text}</span>
          </div>
        )}
        <div className="meta-item">
          <span className="meta-item-label">Search Method</span>
          <MethodBadge method={searchResponse.query_type} />
        </div>
      </div>

      <div className="page-header-row">
        <div>
          <h1 className="page-title">
            Search Results
            <img src={greenLeafImg} alt="" className="page-title-leaf" />
          </h1>
          <p className="page-subtitle">
            Showing {filteredResults.length} results for &ldquo;{queryLabel}&rdquo;
          </p>
        </div>
      </div>

      <div className="results-toolbar">
        <button type="button" className={`filter-chip${typeFilter === null ? " active" : ""}`} onClick={() => { setTypeFilter(null); setCurrentPage(1); }}>
          All
        </button>
        {TYPE_FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            className={`filter-chip${typeFilter === f.id ? " active" : ""}`}
            onClick={() => handleTypeFilterToggle(f.id)}
          >
            <Icon name={f.icon} size={14} />
            {f.label}
          </button>
        ))}
        <div className="results-toolbar__sort">
          <select className="select-input" value={sortBy} onChange={(e) => handleSortChange(e.target.value)} aria-label="Sort by">
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.id} value={opt.id}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {pagedResults.length === 0 ? (
        <p className="text-muted">No results match these filters.</p>
      ) : (
        <div className="results-grid">
          {pagedResults.map((result) => (
            <ResultCard key={result.result_id} result={result} searchMethod={searchResponse.query_type} />
          ))}
        </div>
      )}

      <Pagination currentPage={safePage} totalPages={totalPages} onPageChange={setCurrentPage} />
    </div>
  );
}
