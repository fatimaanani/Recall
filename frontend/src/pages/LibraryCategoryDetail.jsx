import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import "../styles/pages/LibraryCategoryDetail.css";

import Icon from "../components/Icon";
import AssetPlaceholder from "../components/AssetPlaceholder";
import MediaCard from "../components/MediaCard";
import * as categoryService from "../services/categoryService";
import * as videoService from "../services/videoService";
import flowerBranchImg from "../assets/decorations/flowerBranch-trimmed.png";
import branchImg from "../assets/decorations/branch-trimmed.png";

function slugify(name) {
  return name.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

// Collection detail page, resolves categorySlug to a category id
export default function LibraryCategoryDetail({ basePath = "/library" }) {
  const { categorySlug } = useParams();
  const navigate = useNavigate();

  const [allCategories, setAllCategories] = useState([]);
  const [isLoadingCategories, setIsLoadingCategories] = useState(true);
  const [categoriesError, setCategoriesError] = useState("");

  const [category, setCategory] = useState(null);
  const [videos, setVideos] = useState([]);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [notFound, setNotFound] = useState(false);

  const [openMenuId, setOpenMenuId] = useState(null);

  // Collection-level "..." menu (title), separate from per-video openMenuId
  const [collectionMenuOpen, setCollectionMenuOpen] = useState(false);
  const [isRenamingCollection, setIsRenamingCollection] = useState(false);
  const [collectionRenameValue, setCollectionRenameValue] = useState("");

  useEffect(() => {
    categoryService
      .listCategories()
      .then(setAllCategories)
      .catch(() => setCategoriesError("Couldn't load your collections. Please try again."))
      .finally(() => setIsLoadingCategories(false));
  }, []);

  // Resolved fresh every render, never stale
  const matchedId = allCategories.find((c) => slugify(c.name) === categorySlug)?.id;

  function loadDetail(categoryId) {
    setIsLoadingDetail(true);
    setNotFound(false);
    categoryService
      .getCategoryDetail(categoryId)
      .then((detail) => {
        setCategory({ id: detail.id, name: detail.name, video_count: detail.video_count });
        setVideos(detail.videos);
      })
      // 404 or any lookup failure, same not-found treatment as no matching slug
      .catch(() => setNotFound(true))
      .finally(() => setIsLoadingDetail(false));
  }

  useEffect(() => {
    // Reset before (re)resolving, avoids showing stale collection's videos
    setCategory(null);
    setVideos([]);
    setNotFound(false);
    if (matchedId != null) loadDetail(matchedId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matchedId]);

  // Re-fetch this collection's detail, used after add/remove-from-collection
  function refreshDetail() {
    if (category) loadDetail(category.id);
  }

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

  useEffect(() => {
    if (!collectionMenuOpen) return undefined;
    function handleClickOutside(event) {
      if (!event.target.closest(".menu-wrap")) {
        setCollectionMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [collectionMenuOpen]);

  function startRenameCollection() {
    if (!category) return;
    setCollectionRenameValue(category.name);
    setIsRenamingCollection(true);
    setCollectionMenuOpen(false);
  }

  function cancelRenameCollection() {
    setIsRenamingCollection(false);
    setCollectionRenameValue("");
  }

  function confirmRenameCollection() {
    const name = collectionRenameValue.trim();
    if (!name || !category) return;
    categoryService
      .renameCategory(category.id, name)
      .then((updated) => {
        setCategory((prev) => (prev ? { ...prev, name: updated.name } : prev));
        setIsRenamingCollection(false);
        // The route is keyed by a slug derived from the name, so the URL must follow the rename or it'll 404 as "not found".
        navigate(`${basePath}/categories/${slugify(updated.name)}`, { replace: true });
      })
      .catch(() => {
        // Leave input open so the user can see it didn't save and retry.
      });
  }

  function handleVideoRenamed(updatedVideo) {
    setVideos((prev) => prev.map((v) => (v.id === updatedVideo.id ? updatedVideo : v)));
  }

  // Deletes the video itself, not just its membership here
  function handleDeleteVideo(videoId) {
    setOpenMenuId(null);
    videoService
      .deleteVideo(videoId)
      .then(() => setVideos((prev) => prev.filter((v) => v.id !== videoId)))
      .catch(() => {});
  }

  // Removing from this collection drops the card, removing from another just refreshes chips
  function handleRemoveFromCollection(videoId, categoryId) {
    setOpenMenuId(null);
    categoryService
      .removeVideoFromCategory(categoryId, videoId)
      .then(() => {
        if (category && categoryId === category.id) {
          setVideos((prev) => prev.filter((v) => v.id !== videoId));
          setCategory((prev) => (prev ? { ...prev, video_count: prev.video_count - 1 } : prev));
        } else {
          refreshDetail();
        }
      })
      .catch(() => {});
  }

  // Adding never changes what belongs on this page, just refreshes chips
  function handleAddToCollection(videoId, categoryId) {
    setOpenMenuId(null);
    categoryService
      .addVideoToCategory(categoryId, videoId)
      .then(() => refreshDetail())
      .catch(() => {});
  }

  const isLoading = isLoadingCategories || (matchedId != null && isLoadingDetail && !category);
  const showNotFound = !isLoadingCategories && (categoriesError ? false : matchedId == null || notFound) && !category;

  return (
    <div>
      <Link to={`${basePath}/categories`} className="back-to-library">
        <Icon name="arrow-left" size={14} />
        Back to Collections
      </Link>

      <div className="page-header-row">
        <div>
          {isRenamingCollection ? (
            <div className="collection-create-row">
              <input
                type="text"
                className="text-input"
                value={collectionRenameValue}
                onChange={(e) => setCollectionRenameValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") confirmRenameCollection();
                  if (e.key === "Escape") cancelRenameCollection();
                }}
                autoFocus
              />
              <button
                type="button"
                className="collection-create-confirm"
                aria-label="Save name"
                disabled={!collectionRenameValue.trim()}
                onClick={confirmRenameCollection}
              >
                <Icon name="check" size={14} />
              </button>
            </div>
          ) : (
            <h1 className="page-title">
              {category ? category.name : categorySlug}
              {category && (
                <span className="menu-wrap">
                  <button
                    type="button"
                    className="menu-trigger"
                    aria-label="Collection options"
                    onClick={() => setCollectionMenuOpen((v) => !v)}
                  >
                    <Icon name="more-vertical" size={18} />
                  </button>
                  {collectionMenuOpen && (
                    <div className="menu-dropdown">
                      <button type="button" onClick={startRenameCollection}>Rename Collection</button>
                    </div>
                  )}
                </span>
              )}
            </h1>
          )}
          <p className="page-subtitle">
            {category
              ? `${category.video_count} ${category.video_count === 1 ? "item" : "items"} in this collection.`
              : "Media in this collection."}
          </p>
        </div>
      </div>

      {isLoading ? (
        <p className="text-muted">Loading this collection...</p>
      ) : categoriesError ? (
        <p style={{ color: "var(--color-danger)" }}>{categoriesError}</p>
      ) : showNotFound ? (
        <div className="category-detail-placeholder">
          <AssetPlaceholder path="assets/collections/not-found.png" width={96} height={96} />
          <p>This collection doesn&apos;t exist, or you don&apos;t have access to it.</p>
        </div>
      ) : videos.length === 0 ? (
        <div className="category-detail-placeholder">
          <AssetPlaceholder path={`assets/collections/${categorySlug}.png`} width={96} height={96} />
          <p>This collection is empty.</p>
        </div>
      ) : (
        <div className="category-detail-grid media-grid">
          {videos.map((video) => (
            <MediaCard
              key={video.id}
              video={video}
              basePath={basePath}
              allCategories={allCategories}
              isMenuOpen={openMenuId === video.id}
              onToggleMenu={() => setOpenMenuId((current) => (current === video.id ? null : video.id))}
              onCloseMenu={() => setOpenMenuId(null)}
              onRenamed={handleVideoRenamed}
              onDelete={handleDeleteVideo}
              onRemoveFromCollection={handleRemoveFromCollection}
              onAddToCollection={handleAddToCollection}
            />
          ))}
        </div>
      )}

      <div className="page-corner-decorations">
        <img src={branchImg} alt="" className="page-corner-decorations__img page-corner-decorations__img--left" />
        <img src={flowerBranchImg} alt="" className="page-corner-decorations__img page-corner-decorations__img--right" />
      </div>
    </div>
  );
}
