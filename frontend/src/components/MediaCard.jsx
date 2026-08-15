import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import "./MediaCard.css";

import Icon from "./Icon";
import AssetPlaceholder from "./AssetPlaceholder";
import { StatusBadge } from "./Badge";
import * as videoService from "../services/videoService";
import { useProtectedImage } from "../hooks/useProtectedImage";

const MEDIA_TYPE_BADGE = {
  video: { icon: "play", className: "media-card__type-badge--video" },
  audio: { icon: "music", className: "media-card__type-badge--audio" },
};

const STATUS_LABEL = {
  uploaded: "Uploaded",
  processing: "Processing",
  ready: "Processed",
  failed: "Failed",
};

// Processing error text, collapsed + capped for display
const MAX_ERROR_DISPLAY_LENGTH = 140;

function formatProcessingError(message) {
  if (!message) return "Processing failed.";
  const singleLine = message.replace(/\s+/g, " ").trim();
  if (singleLine.length <= MAX_ERROR_DISPLAY_LENGTH) return singleLine;
  return `${singleLine.slice(0, MAX_ERROR_DISPLAY_LENGTH - 1)}…`;
}

// Duration display, "H:MM:SS" / "MM:SS"
function formatDuration(seconds) {
  if (seconds == null) return "--:--";
  const total = Math.round(seconds);
  const hrs = Math.floor(total / 3600);
  const mins = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return hrs > 0 ? `${hrs}:${pad(mins)}:${pad(secs)}` : `${mins}:${pad(secs)}`;
}

function formatDate(isoString) {
  return new Date(isoString).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function MediaCard({
  video,
  allCategories,
  isMenuOpen,
  onToggleMenu,
  onCloseMenu,
  onRenamed,
  onDelete,
  onRemoveFromCollection,
  onAddToCollection,
  // Failed-video only
  isRetrying = false,
  retryError = null,
  onRetry,
  basePath = "/library",
}) {
  const isFailed = video.status === "failed";
  const navigate = useNavigate();
  const detailsPath = `${basePath}/upload-details/${video.id}`;
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(video.title);
  // Add-to-collection submenu, collapses when menu closes
  const [showAddToCollection, setShowAddToCollection] = useState(false);

  const assignedCategoryIds = new Set(video.categories.map((c) => c.id));
  const availableCategories = allCategories.filter((c) => !assignedCategoryIds.has(c.id));

  useEffect(() => {
    if (!isMenuOpen) setShowAddToCollection(false);
  }, [isMenuOpen]);

  // Protected thumbnail fetch, only if has_thumbnail is set
  const thumbnailUrl = useProtectedImage(video.has_thumbnail ? videoService.getThumbnailPath(video.id) : null);
  const typeBadge = MEDIA_TYPE_BADGE[video.media_type] ?? MEDIA_TYPE_BADGE.video;

  // Audio never has a thumbnail, omit the whole block (not just its contents)
  const hasVisualThumbnail = video.media_type !== "audio";

  function startRename() {
    setRenameValue(video.title);
    setIsRenaming(true);
    onCloseMenu();
  }

  function cancelRename() {
    setIsRenaming(false);
    setRenameValue(video.title);
  }

  function confirmRename() {
    const title = renameValue.trim();
    if (!title) return;
    videoService
      .renameVideo(video.id, title)
      .then((updated) => {
        onRenamed(updated);
        setIsRenaming(false);
      })
      .catch(() => {
        // Leave input open so the user can see it didn't save and retry
      });
  }

  // Card itself is the click/keyboard nav target since audio uploads have no thumbnail Link; every interactive descendant stops propagation so it doesn't also trigger this.
  function openDetails() {
    navigate(detailsPath);
  }

  function handleCardKeyDown(event) {
    if (event.key === "Enter") {
      event.preventDefault();
      openDetails();
    }
  }

  return (
    <article
      className="media-card"
      role="link"
      tabIndex={0}
      aria-label={`Open ${video.title}`}
      onClick={openDetails}
      onKeyDown={handleCardKeyDown}
    >
      {hasVisualThumbnail && (
        <Link
          to={detailsPath}
          className="media-card__thumb"
          aria-label={`Open ${video.title}`}
          onClick={(e) => e.stopPropagation()}
        >
          <span className={`media-card__type-badge ${typeBadge.className}`}>
            <Icon name={typeBadge.icon} size={13} />
          </span>
          {thumbnailUrl ? (
            <img src={thumbnailUrl} alt="" className="media-card__thumb-img" />
          ) : (
            <AssetPlaceholder path={`assets/thumbnails/${video.id}.png`} width={56} height={56} />
          )}
          <span className="media-card__duration">{formatDuration(video.duration_seconds)}</span>
        </Link>
      )}
      <div className="media-card__body">
        {isRenaming ? (
          <div
            className="collection-create-row"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
          >
            <input
              type="text"
              className="text-input"
              value={renameValue}
              onChange={(e) => setRenameValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") confirmRename();
                if (e.key === "Escape") cancelRename();
              }}
              autoFocus
            />
            <button
              type="button"
              className="collection-create-confirm"
              aria-label="Save title"
              disabled={!renameValue.trim()}
              onClick={confirmRename}
            >
              <Icon name="check" size={14} />
            </button>
          </div>
        ) : (
          <p className="media-card__title">{video.title}</p>
        )}
        <p className="media-card__meta">
          <Icon name="folder" size={12} />{" "}
          {video.categories.length > 0
            ? video.categories.map((c) => c.name).join(", ")
            : "Uncategorized"}
        </p>
        <p className="media-card__meta">
          <Icon name="calendar" size={12} /> {formatDate(video.uploaded_at)}
        </p>
        {isFailed && <p className="form-error">{formatProcessingError(video.processing_error)}</p>}
        {retryError && <p className="form-error">{retryError}</p>}
        <div className="media-card__footer">
          <StatusBadge status={video.status} label={STATUS_LABEL[video.status] ?? video.status} />
          <div className="menu-wrap" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="menu-trigger" aria-label="Media options" onClick={onToggleMenu}>
              <Icon name="more-vertical" size={16} />
            </button>
            {isMenuOpen && (
              <div className="menu-dropdown">
                {isFailed ? (
                  // Failed, only Retry Processing and Delete apply
                  <>
                    {onRetry && (
                      <button type="button" disabled={isRetrying} onClick={() => onRetry(video.id)}>
                        {isRetrying ? "Retrying..." : "Retry Processing"}
                      </button>
                    )}
                    <button type="button" className="danger" onClick={() => onDelete(video.id)}>
                      Delete Upload
                    </button>
                  </>
                ) : (
                  <>
                    <button type="button" onClick={startRename}>
                      Rename Upload
                    </button>
                    <button
                      type="button"
                      className="menu-dropdown__submenu-toggle"
                      aria-expanded={showAddToCollection}
                      onClick={() => setShowAddToCollection((v) => !v)}
                    >
                      <span>Add to Collection</span>
                      <Icon name={showAddToCollection ? "chevron-down" : "chevron-right"} size={14} />
                    </button>
                    {showAddToCollection && (
                      <div className="menu-dropdown__submenu">
                        {allCategories.length === 0 ? (
                          <p className="menu-dropdown__submenu-empty">You don't have any collections yet.</p>
                        ) : availableCategories.length === 0 ? (
                          <p className="menu-dropdown__submenu-empty">Already in every collection.</p>
                        ) : (
                          availableCategories.map((c) => (
                            <button
                              key={c.id}
                              type="button"
                              onClick={() => onAddToCollection(video.id, c.id)}
                            >
                              {c.name}
                            </button>
                          ))
                        )}
                      </div>
                    )}
                    {video.categories.map((c) => (
                      <button key={c.id} type="button" onClick={() => onRemoveFromCollection(video.id, c.id)}>
                        Remove from {c.name}
                      </button>
                    ))}
                    <button type="button" className="danger" onClick={() => onDelete(video.id)}>
                      Delete Upload
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}
