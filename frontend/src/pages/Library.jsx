import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import "../styles/pages/Library.css";

import Icon from "../components/Icon";
import MediaCard from "../components/MediaCard";
import Pagination from "../components/Pagination";
import * as videoService from "../services/videoService";
import * as categoryService from "../services/categoryService";
import { getErrorMessage } from "../services/apiClient";
import greenLeafImg from "../assets/decorations/greenLeaf-trimmed.png";
import libraryAboveCardMascotImg from "../assets/mascots/libraryAboveCardMascot.png";
import libraryMascotBubbleImg from "../assets/mascots/libraryMascotBubble.png";
import flowerBranchImg from "../assets/decorations/flowerBranch-trimmed.png";
import branchImg from "../assets/decorations/branch-trimmed.png";

const CATEGORY_FILTERS = [
  { id: "video", label: "Videos", icon: "film" },
  { id: "audio", label: "Audio", icon: "music" },
  { id: "other", label: "Others", icon: "file-text" },
];

const SORT_OPTIONS = [
  { id: "newest", label: "Newest Added" },
  { id: "oldest", label: "Oldest Added" },
  { id: "longest", label: "Longest Duration" },
  { id: "shortest", label: "Shortest Duration" },
];

// Sort comparators, null duration treated as 0
const SORT_COMPARATORS = {
  newest: (a, b) => new Date(b.uploaded_at) - new Date(a.uploaded_at),
  oldest: (a, b) => new Date(a.uploaded_at) - new Date(b.uploaded_at),
  longest: (a, b) => (b.duration_seconds ?? 0) - (a.duration_seconds ?? 0),
  shortest: (a, b) => (a.duration_seconds ?? 0) - (b.duration_seconds ?? 0),
};

// Collection name -> URL slug
function slugify(name) {
  return name.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

// Library page, basePath/hideSharedScope let this mount at /library (user) or /admin/my-uploads (admin)
export default function Library({ basePath = "/library", hideSharedScope = false }) {
  const [videos, setVideos] = useState([]);
  const [isLoadingVideos, setIsLoadingVideos] = useState(true);
  const [videosError, setVideosError] = useState("");

  const [categories, setCategories] = useState([]);

  useEffect(() => {
    refreshVideos();
    refreshCategories();
  }, []);

  function refreshVideos() {
    setIsLoadingVideos(true);
    setVideosError("");
    videoService
      .listVideos()
      .then(setVideos)
      .catch(() => setVideosError("Couldn't load your library. Please try again."))
      .finally(() => setIsLoadingVideos(false));
  }

  function refreshCategories() {
    categoryService.listCategories().then(setCategories).catch(() => {});
  }

  const [openMenuId, setOpenMenuId] = useState(null);

  useEffect(() => {
    if (openMenuId === null) return undefined;
    function handleClickOutside(event) {
      if (!event.target.closest(".menu-wrap")) {
        setOpenMenuId(null);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [openMenuId]);

  // Retry Processing state, per-video retry-in-flight + request error
  const [retryingIds, setRetryingIds] = useState(() => new Set());
  const [retryErrors, setRetryErrors] = useState({});

  // Status polling, one interval per video id
  const pollingRef = useRef(new Map());

  function stopPolling(videoId) {
    const intervalId = pollingRef.current.get(videoId);
    if (intervalId) {
      clearInterval(intervalId);
      pollingRef.current.delete(videoId);
    }
  }

  function startPolling(videoId) {
    stopPolling(videoId);
    const intervalId = setInterval(() => {
      videoService
        .getVideo(videoId)
        .then((updated) => {
          setVideos((prev) => prev.map((v) => (v.id === updated.id ? updated : v)));
          if (updated.status === "ready" || updated.status === "failed") {
            stopPolling(videoId);
          }
        })
        .catch(() => {
          // Transient fetch error, stop polling rather than spin forever
          stopPolling(videoId);
        });
    }, 3000);
    pollingRef.current.set(videoId, intervalId);
  }

  useEffect(() => {
    return () => {
      pollingRef.current.forEach((intervalId) => clearInterval(intervalId));
      pollingRef.current.clear();
    };
  }, []);

  function handleRetryProcessing(videoId) {
    setRetryingIds((prev) => new Set(prev).add(videoId));
    setRetryErrors((prev) => {
      if (!(videoId in prev)) return prev;
      const next = { ...prev };
      delete next[videoId];
      return next;
    });
    videoService
      .reprocessVideo(videoId)
      .then((updated) => {
        // Reflect immediately, then poll until it settles
        setVideos((prev) => prev.map((v) => (v.id === updated.id ? updated : v)));
        startPolling(videoId);
      })
      .catch((err) => {
        setRetryErrors((prev) => ({
          ...prev,
          [videoId]: getErrorMessage(err, "Couldn't retry processing. Please try again."),
        }));
      })
      .finally(() => {
        setRetryingIds((prev) => {
          const next = new Set(prev);
          next.delete(videoId);
          return next;
        });
      });
  }

  // Grid/List toggle, not persisted
  const [viewMode, setViewMode] = useState("grid");

  // Filter/sort/pagination state, categoryFilter toggles off like quickFilter
  const [categoryFilter, setCategoryFilter] = useState(null);
  const [scope, setScope] = useState("uploads");
  const [sortBy, setSortBy] = useState("newest");
  const [currentPage, setCurrentPage] = useState(1);

  // Quick Filters, mutually exclusive, null means neither active
  const [quickFilter, setQuickFilter] = useState(null);

  const [showCreateCollection, setShowCreateCollection] = useState(false);
  const [newCollectionName, setNewCollectionName] = useState("");
  const [createCollectionError, setCreateCollectionError] = useState("");
  const sidebarCollections = categories.slice(0, 5);

  // Library shows finished processing only, ready or failed
  const libraryVideos = videos.filter((video) => video.status === "ready" || video.status === "failed");

  // Category -> media_type, Scope -> visibility, Quick Filter -> has_subtitles, then Sort
  const visibleVideos = libraryVideos
    .filter((video) => categoryFilter === null || video.media_type === categoryFilter)
    .filter((video) => video.visibility === (scope === "shared" ? "shared" : "private"))
    .filter((video) => {
      if (quickFilter === "with_subtitles") return video.has_subtitles;
      if (quickFilter === "without_subtitles") return !video.has_subtitles;
      return true;
    })
    .slice()
    .sort(SORT_COMPARATORS[sortBy]);

  const PAGE_SIZE = 15;
  const totalPages = Math.max(1, Math.ceil(visibleVideos.length / PAGE_SIZE));
  const safePage = Math.min(currentPage, totalPages);
  const pageStart = (safePage - 1) * PAGE_SIZE;
  const pagedVideos = visibleVideos.slice(pageStart, pageStart + PAGE_SIZE);

  function handleCategoryChange(id) {
    setCategoryFilter((current) => (current === id ? null : id));
    setCurrentPage(1);
  }

  function handleScopeChange(value) {
    setScope(value);
    setCurrentPage(1);
  }

  function handleSortChange(value) {
    setSortBy(value);
    setCurrentPage(1);
  }

  function handleQuickFilterToggle(id) {
    setQuickFilter((current) => (current === id ? null : id));
    setCurrentPage(1);
  }

  // MediaCard performs the rename itself, this just folds the result back in
  function handleVideoRenamed(updatedVideo) {
    setVideos((prev) => prev.map((v) => (v.id === updatedVideo.id ? updatedVideo : v)));
  }

  function handleDeleteVideo(videoId) {
    setOpenMenuId(null);
    videoService
      .deleteVideo(videoId)
      .then(() => {
        setVideos((prev) => prev.filter((v) => v.id !== videoId));
        refreshCategories();
      })
      .catch(() => {});
  }

  function handleRemoveFromCollection(videoId, categoryId) {
    setOpenMenuId(null);
    categoryService
      .removeVideoFromCategory(categoryId, videoId)
      .then(() => {
        refreshVideos();
        refreshCategories();
      })
      .catch(() => {});
  }

  function handleAddToCollection(videoId, categoryId) {
    setOpenMenuId(null);
    categoryService
      .addVideoToCategory(categoryId, videoId)
      .then(() => {
        refreshVideos();
        refreshCategories();
      })
      .catch(() => {});
  }

  function handleCreateCollection() {
    const name = newCollectionName.trim();
    if (!name) return;
    categoryService
      .createCategory(name)
      .then((created) => {
        setCategories((prev) => [created, ...prev]);
        setNewCollectionName("");
        setCreateCollectionError("");
        setShowCreateCollection(false);
      })
      .catch((err) => {
        // 409 duplicate name, kept visible in the row
        setCreateCollectionError(err.response?.data?.detail ?? "Couldn't create this collection.");
      });
  }

  function handleCancelCreateCollection() {
    setNewCollectionName("");
    setCreateCollectionError("");
    setShowCreateCollection(false);
  }

  return (
    <div>
      <div className="library-page-header">
        <div>
          <h1 className="page-title">
            Library
            <img src={greenLeafImg} alt="" className="page-title-leaf" />
          </h1>
          <p className="page-subtitle">Your archive of uploaded media. Organized, processed, and ready to search.</p>
        </div>

        <div className="library-header-actions">
          <div className="input-wrap library-search">
            <Icon name="search" size={16} />
            <input type="text" className="text-input" placeholder="Search in library..." />
          </div>
        </div>
      </div>

      <div className="library-layout">
        <div>
          <div className="library-toolbar">
            {!hideSharedScope && (
              <select
                className="select-input library-scope-select"
                value={scope}
                onChange={(e) => handleScopeChange(e.target.value)}
                aria-label="Uploads or Shared library"
              >
                <option value="uploads">Uploads</option>
                <option value="shared">Shared</option>
              </select>
            )}

            {CATEGORY_FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                className={`filter-chip${categoryFilter === f.id ? " active" : ""}`}
                onClick={() => handleCategoryChange(f.id)}
              >
                <Icon name={f.icon} size={14} />
                {f.label}
              </button>
            ))}

            <div className="library-toolbar__view">
              <select
                className="select-input library-sort-select"
                value={sortBy}
                onChange={(e) => handleSortChange(e.target.value)}
                aria-label="Sort by"
              >
                {SORT_OPTIONS.map((opt) => (
                  <option key={opt.id} value={opt.id}>{opt.label}</option>
                ))}
              </select>
              <div className="view-toggle">
                <button
                  type="button"
                  className={`view-toggle__btn${viewMode === "grid" ? " active" : ""}`}
                  aria-label="Grid view"
                  aria-pressed={viewMode === "grid"}
                  onClick={() => setViewMode("grid")}
                >
                  <Icon name="grid" size={16} />
                </button>
                <button
                  type="button"
                  className={`view-toggle__btn${viewMode === "list" ? " active" : ""}`}
                  aria-label="List view"
                  aria-pressed={viewMode === "list"}
                  onClick={() => setViewMode("list")}
                >
                  <Icon name="list" size={16} />
                </button>
              </div>
            </div>
          </div>

          {isLoadingVideos ? (
            <p className="media-grid-empty">Loading your library...</p>
          ) : videosError ? (
            <p className="media-grid-empty" style={{ color: "var(--color-danger)" }}>{videosError}</p>
          ) : visibleVideos.length > 0 ? (
            <div className={`media-grid${viewMode === "list" ? " media-grid--list" : ""}`}>
              {pagedVideos.map((video) => (
                <MediaCard
                  key={video.id}
                  video={video}
                  basePath={basePath}
                  allCategories={categories}
                  isMenuOpen={openMenuId === video.id}
                  onToggleMenu={() => setOpenMenuId((current) => (current === video.id ? null : video.id))}
                  onCloseMenu={() => setOpenMenuId(null)}
                  onRenamed={handleVideoRenamed}
                  onDelete={handleDeleteVideo}
                  onRemoveFromCollection={handleRemoveFromCollection}
                  onAddToCollection={handleAddToCollection}
                  isRetrying={retryingIds.has(video.id)}
                  retryError={retryErrors[video.id] ?? null}
                  onRetry={handleRetryProcessing}
                />
              ))}
            </div>
          ) : (
            <p className="media-grid-empty">No media matches these filters.</p>
          )}

          <Pagination currentPage={safePage} totalPages={totalPages} onPageChange={setCurrentPage} />
        </div>

        <div className="library-side">
          <div className="library-side__mascot library-side__mascot--top">
            <img src={libraryAboveCardMascotImg} alt="" className="library-side__mascot-img library-side__mascot-img--top" />
          </div>

          <div className="ui-card ui-card--alt-bg library-side__collections">
            <div className="ui-card__header-row">
              <h3 style={{ fontSize: 14 }}>Collections</h3>
              <button
                type="button"
                className="menu-trigger"
                aria-label={showCreateCollection ? "Cancel new collection" : "Create new collection"}
                onClick={() => (showCreateCollection ? handleCancelCreateCollection() : setShowCreateCollection(true))}
              >
                <Icon name={showCreateCollection ? "x" : "plus"} size={15} />
              </button>
            </div>

            {showCreateCollection && (
              <div className="collection-create-row" style={{ flexDirection: "column", alignItems: "stretch" }}>
                <div style={{ display: "flex", gap: 6 }}>
                  <input
                    type="text"
                    className="text-input"
                    placeholder="Collection Name"
                    value={newCollectionName}
                    onChange={(e) => setNewCollectionName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleCreateCollection();
                      if (e.key === "Escape") handleCancelCreateCollection();
                    }}
                    autoFocus
                  />
                  <button
                    type="button"
                    className="collection-create-confirm"
                    aria-label="Create collection"
                    disabled={!newCollectionName.trim()}
                    onClick={handleCreateCollection}
                  >
                    <Icon name="check" size={15} />
                  </button>
                </div>
                {createCollectionError && (
                  <p style={{ color: "var(--color-danger)", fontSize: 12, margin: "4px 0 0" }}>{createCollectionError}</p>
                )}
              </div>
            )}

            <ul className="collections-list">
              {sidebarCollections.map((c) => (
                <li key={c.id}>
                  <Link to={`${basePath}/categories/${slugify(c.name)}`} className="collections-list__item">
                    <span><Icon name="folder" size={14} /> {c.name}</span>
                    <strong>{c.video_count}</strong>
                  </Link>
                </li>
              ))}
            </ul>
            <Link to={`${basePath}/categories`} className="view-all-link">
              View all collections <Icon name="arrow-right" size={13} />
            </Link>
          </div>

          <div className="ui-card ui-card--alt-bg library-side__quick-filters">
            <h3 style={{ fontSize: 14 }}>Quick Filters</h3>
            <ul className="quick-filters-list">
              <li>
                <button
                  type="button"
                  className={`quick-filter-btn${quickFilter === "with_subtitles" ? " active" : ""}`}
                  onClick={() => handleQuickFilterToggle("with_subtitles")}
                >
                  <span>With Subtitles</span>
                  <strong>{libraryVideos.filter((v) => v.has_subtitles).length}</strong>
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className={`quick-filter-btn${quickFilter === "without_subtitles" ? " active" : ""}`}
                  onClick={() => handleQuickFilterToggle("without_subtitles")}
                >
                  <span>Without Subtitles</span>
                  <strong>{libraryVideos.filter((v) => !v.has_subtitles).length}</strong>
                </button>
              </li>
            </ul>
          </div>

          <div className="library-side__mascot library-side__mascot--bottom">
            <img src={libraryMascotBubbleImg} alt="Every file you upload becomes part of your personal archive." className="library-side__mascot-img library-side__mascot-img--bottom" />
          </div>
        </div>
      </div>

      <div className="page-corner-decorations">
        <img src={branchImg} alt="" className="page-corner-decorations__img page-corner-decorations__img--left" />
        <img src={flowerBranchImg} alt="" className="page-corner-decorations__img page-corner-decorations__img--right" />
      </div>
    </div>
  );
}
