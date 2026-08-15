import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import Icon from "../../components/Icon";
import AssetPlaceholder from "../../components/AssetPlaceholder";
import { StatusBadge } from "../../components/Badge";
import * as adminService from "../../services/adminService";
import { getErrorMessage } from "../../services/apiClient";
import { useProtectedImage } from "../../hooks/useProtectedImage";
import "../../styles/pages/admin/UserManagement.css";

const STATUS_LABEL = {
  uploaded: "Uploaded",
  processing: "Processing",
  ready: "Processed",
  failed: "Failed",
};

function formatBytes(bytes) {
  if (bytes >= 1_000_000_000) return `${(bytes / 1_000_000_000).toFixed(2)} GB`;
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  if (bytes > 0) return `${Math.max(1, Math.round(bytes / 1000))} KB`;
  return "0 KB";
}

function formatDuration(seconds) {
  if (seconds == null) return "--:--";
  const total = Math.round(seconds);
  const hrs = Math.floor(total / 3600);
  const mins = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return hrs > 0 ? `${hrs}:${pad(mins)}:${pad(secs)}` : `${mins}:${pad(secs)}`;
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "--";
}

// File type from filename extension, falls back to mime_type
function fileTypeFromVideo(video) {
  const fromName = video.original_filename?.split(".").pop();
  return (fromName || video.mime_type || "unknown").toUpperCase();
}

// Admin upload detail page
export default function AdminUploadDetail() {
  const { videoId } = useParams();
  const navigate = useNavigate();

  const [video, setVideo] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    setIsLoading(true);
    adminService
      .getUploadDetail(videoId)
      .then((data) => {
        setVideo(data);
        setErrorMessage("");
      })
      .catch((err) => setErrorMessage(getErrorMessage(err, "Couldn't load this upload.")))
      .finally(() => setIsLoading(false));
  }, [videoId]);

  const thumbnailUrl = useProtectedImage(
    video?.has_thumbnail ? adminService.getUploadThumbnailPath(videoId) : null
  );

  function handleDelete() {
    if (!video) return;
    if (!window.confirm(`Permanently delete "${video.title}"? This can't be undone.`)) {
      return;
    }
    setIsDeleting(true);
    adminService
      .deleteUpload(video.id)
      .then(() => {
        // Return to User Management, reopen owning user's View panel
        navigate("/admin/users", { state: { reopenUserId: video.owner_id } });
      })
      .catch((err) => {
        setErrorMessage(getErrorMessage(err, "Couldn't delete this upload."));
        setIsDeleting(false);
      });
  }

  return (
    <div>
      <Link to="/admin/users" className="back-to-library">
        <Icon name="arrow-left" size={14} />
        Back to User Management
      </Link>

      <div className="page-header-row">
        <div>
          <h1 className="page-title">Upload Details</h1>
          <p className="page-subtitle">Full details for one user&apos;s upload.</p>
        </div>
        {video && (
          <button
            type="button"
            className="btn btn--danger-outline btn--sm"
            disabled={isDeleting}
            onClick={handleDelete}
          >
            <Icon name="trash-2" size={14} />
            <span>{isDeleting ? "Deleting..." : "Delete Upload"}</span>
          </button>
        )}
      </div>

      {errorMessage && <p className="form-error" style={{ marginBottom: 12 }}>{errorMessage}</p>}

      {isLoading ? (
        <p className="text-muted">Loading upload...</p>
      ) : !video ? null : (
        <div className="ui-card" style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
          <div style={{ width: 220, flexShrink: 0 }}>
            {thumbnailUrl ? (
              <img src={thumbnailUrl} alt="" style={{ width: "100%", borderRadius: 8, display: "block" }} />
            ) : (
              <AssetPlaceholder path={`assets/thumbnails/${video.id}.png`} width="100%" height={140} />
            )}
          </div>

          <div style={{ flex: 1, minWidth: 260 }}>
            <h2 style={{ margin: "0 0 4px", fontSize: 18 }}>{video.title}</h2>
            <p className="text-muted" style={{ margin: "0 0 12px" }}>{video.original_filename}</p>

            <div className="view-panel__row">
              <span className="view-panel__label">Status</span>
              <span className="view-panel__value">
                <StatusBadge status={video.status} label={STATUS_LABEL[video.status] ?? video.status} />
              </span>
            </div>
            <div className="view-panel__row">
              <span className="view-panel__label">File Type</span>
              <span className="view-panel__value">{fileTypeFromVideo(video)}</span>
            </div>
            <div className="view-panel__row">
              <span className="view-panel__label">File Size</span>
              <span className="view-panel__value">{formatBytes(video.file_size_bytes)}</span>
            </div>
            <div className="view-panel__row">
              <span className="view-panel__label">Duration</span>
              <span className="view-panel__value">{formatDuration(video.duration_seconds)}</span>
            </div>
            <div className="view-panel__row">
              <span className="view-panel__label">Subtitles / Transcript</span>
              <span className="view-panel__value">{video.has_subtitles ? "Available" : "Not available"}</span>
            </div>
            <div className="view-panel__row">
              <span className="view-panel__label">Categories</span>
              <span className="view-panel__value">
                {video.categories.length > 0 ? video.categories.map((c) => c.name).join(", ") : "--"}
              </span>
            </div>
            <div className="view-panel__row">
              <span className="view-panel__label">Uploaded</span>
              <span className="view-panel__value">{formatDate(video.uploaded_at)}</span>
            </div>

            {video.status === "failed" && video.processing_error && (
              <p className="form-error" style={{ marginTop: 12 }}>{video.processing_error}</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
