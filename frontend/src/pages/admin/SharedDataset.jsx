import { useEffect, useState } from "react";

import Icon from "../../components/Icon";
import AssetPlaceholder from "../../components/AssetPlaceholder";
import { StatusBadge } from "../../components/Badge";
import * as videoService from "../../services/videoService";
import { getErrorMessage } from "../../services/apiClient";
import { useProtectedImage } from "../../hooks/useProtectedImage";
import { useStagedUploadQueue, MAX_STAGED_FILES } from "../../hooks/useStagedUploadQueue";
import "../../styles/pages/admin/SharedDataset.css";
import "../../components/MediaCard.css";
import "../../components/UploadDropzone.css";
import greenLeafImg from "../../assets/decorations/greenLeaf-trimmed.png";

const STATUS_LABEL = {
  uploaded: "Uploaded",
  processing: "Processing",
  ready: "Processed",
  failed: "Failed",
};

function formatDuration(seconds) {
  if (seconds == null) return "--:--";
  const total = Math.round(seconds);
  const hrs = Math.floor(total / 3600);
  const mins = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return hrs > 0 ? `${hrs}:${pad(mins)}:${pad(secs)}` : `${mins}:${pad(secs)}`;
}

function SharedVideoCard({ video, onRemove }) {
  const thumbnailUrl = useProtectedImage(video.has_thumbnail ? videoService.getThumbnailPath(video.id) : null);

  return (
    <article className="media-card">
      <div className="media-card__thumb">
        {thumbnailUrl ? (
          <img src={thumbnailUrl} alt="" className="media-card__thumb-img" />
        ) : (
          <AssetPlaceholder path={`assets/thumbnails/${video.id}.png`} width={64} height={64} />
        )}
        <span className="media-card__duration">{formatDuration(video.duration_seconds)}</span>
      </div>
      <div className="media-card__body">
        <p className="media-card__title">{video.title}</p>
        <p className="media-card__meta">{video.media_type === "audio" ? "Audio" : "Video"}</p>
        <StatusBadge status={video.status} label={STATUS_LABEL[video.status] ?? video.status} />
        <button
          type="button"
          className="btn btn--danger-outline btn--sm btn--block"
          style={{ marginTop: 8 }}
          onClick={() => onRemove(video.id)}
        >
          <Icon name="trash-2" size={13} />
          <span>Remove</span>
        </button>
      </div>
    </article>
  );
}

// Shared Dataset page, admin-curated shared media
export default function SharedDataset() {
  const [videos, setVideos] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    refreshVideos();
  }, []);

  function refreshVideos() {
    setIsLoading(true);
    videoService
      .listVideos()
      .then((data) => {
        setVideos(data.filter((v) => v.visibility === "shared"));
        setErrorMessage("");
      })
      .catch((err) => setErrorMessage(getErrorMessage(err, "Couldn't load the shared dataset.")))
      .finally(() => setIsLoading(false));
  }

  const upload = useStagedUploadQueue({ onUploadSuccess: refreshVideos });
  const {
    stagedFiles,
    stagingError,
    isDragOver,
    queue,
    handleFileChange,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    removeStagedFile,
    handleConfirmUpload,
    dismissQueueItem,
  } = upload;

  function handleRemove(videoId) {
    if (!window.confirm("Remove this video from the shared dataset? This can't be undone.")) {
      return;
    }
    videoService
      .deleteVideo(videoId)
      .then(() => refreshVideos())
      .catch((err) => setErrorMessage(getErrorMessage(err, "Couldn't remove that video.")));
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">
          Shared Dataset
          <img src={greenLeafImg} alt="" className="page-title-leaf" />
        </h1>
        <p className="page-subtitle">Media available to every user via the Shared Library search scope.</p>
      </div>

      {errorMessage && <p className="form-error" style={{ marginBottom: 12 }}>{errorMessage}</p>}

      <div
        className={`upload-dropzone${isDragOver ? " shared-dropzone--drag-over" : ""}`}
        style={{ padding: 24, marginBottom: 24 }}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <Icon name="upload" size={28} />
        <p style={{ marginTop: 8, fontWeight: 500, fontFamily: "var(--font-extended)" }}>Add video to shared dataset</p>
        <label className="btn btn--admin" style={{ cursor: "pointer", marginTop: 8 }}>
          <Icon name="folder" size={15} />
          <span>Browse Files</span>
          <input type="file" accept=".mp4,.mkv,.mov" multiple style={{ display: "none" }} onChange={handleFileChange} />
        </label>
        <p className="upload-dropzone__hint">
          Supports: MP4, MKV, MOV &middot; Max file size: 5 GB &middot; Up to {MAX_STAGED_FILES} files at a time
        </p>
      </div>

      {(stagedFiles.length > 0 || stagingError) && (
        <div className="shared-staged-card">
          <div className="page-header-row" style={{ marginBottom: 8 }}>
            <h3 style={{ fontSize: 14 }}>Selected Files ({stagedFiles.length})</h3>
            <button
              type="button"
              className="btn btn--admin btn--sm"
              disabled={stagedFiles.length === 0}
              onClick={handleConfirmUpload}
            >
              <Icon name="check" size={14} />
              <span>Upload</span>
            </button>
          </div>
          {stagedFiles.map((staged) => (
            <div key={staged.stagedId} className="shared-staged-row">
              <span className="shared-staged-row__name">{staged.fileName}</span>
              <span className="shared-staged-row__meta">{staged.sizeLabel}</span>
              <button
                type="button"
                className="shared-staged-row__remove"
                aria-label={`Remove ${staged.fileName}`}
                onClick={() => removeStagedFile(staged.stagedId)}
              >
                <Icon name="x" size={14} />
              </button>
            </div>
          ))}
          {stagingError && <p className="form-error">{stagingError}</p>}
        </div>
      )}

      {queue.length > 0 && (
        <div className="shared-staged-card">
          <h3 style={{ fontSize: 14, marginBottom: 8 }}>Upload Queue ({queue.length})</h3>
          {queue.map((item) => (
            <div key={item.id} className="shared-staged-row">
              <span className="shared-staged-row__name">{item.fileName}</span>
              <span className="shared-staged-row__meta">
                {item.state === "queued" && "Queued"}
                {item.state === "uploading" && `Uploading... ${item.progressPercent}%`}
                {item.state === "processing" && "Processing..."}
                {item.state === "subtitles" && "Generating subtitles..."}
                {item.state === "done" && "Uploaded"}
                {item.state === "error" && (item.errorMessage || "Failed")}
              </span>
              {item.state === "error" && (
                <button
                  type="button"
                  className="shared-staged-row__remove"
                  aria-label={`Dismiss ${item.fileName}`}
                  onClick={() => dismissQueueItem(item.id)}
                >
                  <Icon name="x" size={14} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {isLoading ? (
        <p className="text-muted" style={{ padding: "var(--space-md) 0" }}>Loading shared dataset...</p>
      ) : videos.length === 0 ? (
        <p className="text-muted" style={{ padding: "var(--space-md) 0" }}>No shared media yet.</p>
      ) : (
        <div className="shared-dataset-grid media-grid">
          {videos.map((video) => (
            <SharedVideoCard key={video.id} video={video} onRemove={handleRemove} />
          ))}
        </div>
      )}
    </div>
  );
}
