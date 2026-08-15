import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import "../styles/pages/UploadDetails.css";

import Icon from "../components/Icon";
import AssetPlaceholder from "../components/AssetPlaceholder";
import { StatusBadge, MethodBadge } from "../components/Badge";
import * as videoService from "../services/videoService";
import { getErrorMessage } from "../services/apiClient";
import { useProtectedMedia } from "../hooks/useProtectedMedia";
import { useProtectedImage } from "../hooks/useProtectedImage";
import audioMascotImg from "../assets/mascots/audioMascot.png";
import greenLeafImg from "../assets/decorations/greenLeaf-trimmed.png";

const VALID_VIDEO_ID_PATTERN = /^[1-9]\d*$/;
const PREVIEW_SEGMENT_COUNT = 6;
const SAVED_INITIAL_COUNT = 4;
const SAVED_STEP_COUNT = 3;

const STATUS_LABEL = {
  uploaded: "Uploaded",
  processing: "Processing",
  ready: "Processed",
  failed: "Failed",
};

function formatBytes(bytes) {
  if (bytes == null) return "--";
  if (bytes >= 1_000_000_000) return `${(bytes / 1_000_000_000).toFixed(2)} GB`;
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  if (bytes > 0) return `${Math.max(1, Math.round(bytes / 1000))} KB`;
  return "0 KB";
}

// "H:MM:SS" / "MM:SS", same as MediaCard.jsx
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
  if (!isoString) return "--";
  return new Date(isoString).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

// Transcript row timestamp, "MM:SS" or "H:MM:SS" when useHours is set, so every row in a transcript uses one consistent format.
function formatTimestamp(seconds, useHours) {
  if (seconds == null) return "--:--";
  const total = Math.round(seconds);
  const hrs = Math.floor(total / 3600);
  const mins = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return useHours ? `${hrs}:${pad(mins)}:${pad(secs)}` : `${mins}:${pad(secs)}`;
}

// Real start_time/end_time only, never a computed or guessed end time.
function formatTimestampRange(startTime, endTime, useHours) {
  return `${formatTimestamp(startTime, useHours)} – ${formatTimestamp(endTime, useHours)}`;
}

// Invalid id / not found / unauthorized all render identically, so a private upload owned by someone else looks the same as one that doesn't exist.
function NotFound({ basePath, message }) {
  return (
    <div style={{ textAlign: "center", padding: "64px 16px" }}>
      <p style={{ fontWeight: 500, fontFamily: "var(--font-extended)", fontSize: 16 }}>
        We couldn't find this upload.
      </p>
      <p className="text-muted">{message}</p>
      <Link to={basePath} className="btn btn--primary" style={{ display: "inline-flex", marginTop: 12 }}>
        <Icon name="arrow-left" size={16} />
        <span>Back to Library</span>
      </Link>
    </div>
  );
}

// A dedicated component so useProtectedImage is called at most once per row. The whole row is a single Link; unsaving happens through Scene Viewer's own bookmark icon, not here.
function SavedSceneRow({ scene }) {
  const isAudio = scene.media_type === "audio";
  const thumbnailUrl = useProtectedImage(
    !isAudio && scene.has_thumbnail ? videoService.getThumbnailPath(scene.video_id) : null
  );

  return (
    <Link to={`/scene-viewer/${scene.result_id}`} className="upload-details-saved-row">
      <span className="upload-details-saved-row__thumb">
        {isAudio ? (
          <img src={audioMascotImg} alt="" className="upload-details-saved-row__mascot" />
        ) : thumbnailUrl ? (
          <img src={thumbnailUrl} alt="" />
        ) : (
          <AssetPlaceholder path={`assets/thumbnails/${scene.video_id}.png`} width="100%" height="100%" />
        )}
        <span className="upload-details-saved-row__play">
          <Icon name="play" size={12} />
        </span>
      </span>
      <span className="upload-details-saved-row__body">
        {/* Display label, not a stored title -- GeneratedClip has no human-readable name column. */}
        <span className="upload-details-saved-row__title">
          {scene.video_title} — {formatDuration(scene.start_time)}
        </span>
        <span className="upload-details-saved-row__meta text-muted">{formatDuration(scene.duration)}</span>
      </span>
      <MethodBadge method={scene.search_method} />
    </Link>
  );
}

export default function UploadDetails({ basePath = "/library" }) {
  const { uploadId } = useParams();
  const isValidId = VALID_VIDEO_ID_PATTERN.test(uploadId ?? "");

  const [video, setVideo] = useState(null);
  const [isLoadingVideo, setIsLoadingVideo] = useState(isValidId);
  const [videoError, setVideoError] = useState("");

  const [segments, setSegments] = useState(null);
  const [isLoadingTranscript, setIsLoadingTranscript] = useState(false);
  const [transcriptError, setTranscriptError] = useState("");
  const [isTranscriptExpanded, setIsTranscriptExpanded] = useState(false);

  const [savedScenes, setSavedScenes] = useState(null);
  const [isLoadingSaved, setIsLoadingSaved] = useState(false);
  const [savedError, setSavedError] = useState("");
  const [visibleSavedCount, setVisibleSavedCount] = useState(SAVED_INITIAL_COUNT);

  // Ref to whichever media element is actually mounted (<video> or <audio>, only one renders at a time). Transcript seeking talks to this element directly.
  const mediaRef = useRef(null);
  const [currentTime, setCurrentTime] = useState(0);

  useEffect(() => {
    if (!isValidId) {
      setIsLoadingVideo(false);
      return undefined;
    }
    let cancelled = false;
    setIsLoadingVideo(true);
    setVideoError("");
    videoService
      .getVideo(uploadId)
      .then((data) => {
        if (!cancelled) setVideo(data);
      })
      .catch((err) => {
        if (!cancelled) setVideoError(getErrorMessage(err, "This upload may have been removed, or you may not have access to it."));
      })
      .finally(() => {
        if (!cancelled) setIsLoadingVideo(false);
      });
    return () => {
      cancelled = true;
    };
  }, [uploadId, isValidId]);

  // Fetched exactly once; View All/Show Less afterward is pure client-side state, no second request.
  useEffect(() => {
    if (!video) return undefined;
    let cancelled = false;
    setIsLoadingTranscript(true);
    setTranscriptError("");
    videoService
      .getTranscript(uploadId)
      .then((data) => {
        if (!cancelled) setSegments(data);
      })
      .catch((err) => {
        if (!cancelled) setTranscriptError(getErrorMessage(err, "Couldn't load the transcript."));
      })
      .finally(() => {
        if (!cancelled) setIsLoadingTranscript(false);
      });
    return () => {
      cancelled = true;
    };
  }, [video, uploadId]);

  // Fetched exactly once; View More/Show Less afterward is pure client-side state over the same array, no re-fetching.
  useEffect(() => {
    if (!video) return undefined;
    let cancelled = false;
    setIsLoadingSaved(true);
    setSavedError("");
    videoService
      .listSavedForVideo(uploadId)
      .then((data) => {
        if (!cancelled) setSavedScenes(data);
      })
      .catch((err) => {
        if (!cancelled) setSavedError(getErrorMessage(err, "Couldn't load saved scenes."));
      })
      .finally(() => {
        if (!cancelled) setIsLoadingSaved(false);
      });
    return () => {
      cancelled = true;
    };
  }, [video, uploadId]);

  // Original media, only attempted once processing has actually succeeded.
  const isReady = video?.status === "ready";
  const streamPath = isReady ? videoService.getStreamPath(uploadId) : null;
  const { url: mediaUrl, isLoading: isMediaLoading, error: mediaError } = useProtectedMedia(streamPath);

  // Gates whether transcript timestamps are clickable and whether active-segment highlighting has anything real to track.
  const canSeek = isReady && !mediaError && !!mediaUrl;

  // Listens to the mounted element's native timeupdate event; re-subscribes whenever the element is replaced (new mediaUrl, or a switch between <video>/<audio>).
  useEffect(() => {
    const mediaEl = mediaRef.current;
    if (!mediaEl) return undefined;
    function handleTimeUpdate() {
      setCurrentTime(mediaEl.currentTime);
    }
    mediaEl.addEventListener("timeupdate", handleTimeUpdate);
    return () => mediaEl.removeEventListener("timeupdate", handleTimeUpdate);
  }, [mediaUrl, video?.media_type]);

  function seekToSegment(startTime) {
    const mediaEl = mediaRef.current;
    if (!mediaEl) return;
    mediaEl.currentTime = startTime;
    mediaEl.play().catch(() => {
      // Autoplay can still be blocked in rare browser configurations even
      // on a direct click -- fail silently, the user can press play.
    });
    mediaEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  // One consistent timestamp format for the whole transcript, based on the segment data itself rather than the upload's possibly-absent duration_seconds.
  const useHourFormat = segments != null && segments.some((s) => s.end_time >= 3600);

  if (!isValidId) {
    return (
      <NotFound
        basePath={basePath}
        message="Upload Details opens from your Library -- select an upload to view its details."
      />
    );
  }

  if (isLoadingVideo) {
    return (
      <div>
        <Link to={basePath} className="back-to-library">
          <Icon name="arrow-left" size={14} />
          Back to Library
        </Link>
        <p className="text-muted">Loading upload...</p>
      </div>
    );
  }

  if (!video) {
    return <NotFound basePath={basePath} message={videoError} />;
  }

  function renderMediaArea() {
    if (!isReady) {
      const isFailed = video.status === "failed";
      return (
        <div className="upload-details-player upload-details-player--state">
          <Icon name={isFailed ? "alert-triangle" : "clock"} size={26} />
          <p>
            {isFailed
              ? "This upload failed to process, so playback isn't available."
              : "This upload is still processing. Playback will be available once it's ready."}
          </p>
        </div>
      );
    }
    if (mediaError) {
      return (
        <div className="upload-details-player upload-details-player--state">
          <p>Couldn't load this file. {getErrorMessage(mediaError, "Please try again.")}</p>
        </div>
      );
    }
    if (isMediaLoading || !mediaUrl) {
      return (
        <div className="upload-details-player upload-details-player--state">
          <p>Loading media...</p>
        </div>
      );
    }
    if (video.media_type === "audio") {
      return (
        <div className="upload-details-player upload-details-player--audio">
          <img src={audioMascotImg} alt="" className="upload-details-audio-mascot" />
          <audio ref={mediaRef} src={mediaUrl} controls style={{ width: "90%" }} />
        </div>
      );
    }
    return (
      <div className="upload-details-player">
        <video
          ref={mediaRef}
          src={mediaUrl}
          controls
          style={{ width: "100%", height: "100%", objectFit: "contain" }}
        />
      </div>
    );
  }

  function renderTranscript() {
    if (isLoadingTranscript) return <p className="text-muted">Loading transcript...</p>;
    if (transcriptError) return <p className="form-error">{transcriptError}</p>;
    if (!segments || segments.length === 0) {
      return <p className="text-muted">No transcript available for this upload.</p>;
    }
    const visibleSegments = isTranscriptExpanded ? segments : segments.slice(0, PREVIEW_SEGMENT_COUNT);
    return (
      <>
        <ul className="upload-details-transcript-list">
          {visibleSegments.map((segment) => {
            const isActive = canSeek && currentTime >= segment.start_time && currentTime < segment.end_time;
            const rangeLabel = formatTimestampRange(segment.start_time, segment.end_time, useHourFormat);
            return (
              <li
                key={segment.id}
                className={[
                  "upload-details-transcript-row",
                  canSeek && "upload-details-transcript-row--clickable",
                  isActive && "upload-details-transcript-row--active",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                {canSeek ? (
                  <button
                    type="button"
                    className="upload-details-transcript-time upload-details-transcript-time--clickable"
                    onClick={() => seekToSegment(segment.start_time)}
                    title="Play from this point"
                  >
                    {rangeLabel}
                  </button>
                ) : (
                  <span className="upload-details-transcript-time">{rangeLabel}</span>
                )}
                <span className="upload-details-transcript-text">{segment.text}</span>
              </li>
            );
          })}
        </ul>
        {segments.length > PREVIEW_SEGMENT_COUNT && (
          <button
            type="button"
            className="upload-details-transcript-toggle"
            onClick={() => setIsTranscriptExpanded((v) => !v)}
          >
            <span>{isTranscriptExpanded ? "Show Less" : "View All"}</span>
            <Icon name={isTranscriptExpanded ? "chevron-down" : "chevron-right"} size={13} />
          </button>
        )}
      </>
    );
  }

  function renderSavedScenes() {
    if (isLoadingSaved) return <p className="text-muted">Loading saved scenes...</p>;
    if (savedError) return <p className="form-error">{savedError}</p>;
    if (!savedScenes || savedScenes.length === 0) {
      return <p className="text-muted">No saved scenes yet.</p>;
    }

    const visible = savedScenes.slice(0, visibleSavedCount);
    const hasMore = visibleSavedCount < savedScenes.length;
    const isExpanded = visibleSavedCount > SAVED_INITIAL_COUNT;

    return (
      <>
        <div className="upload-details-saved-list">
          {visible.map((scene) => (
            <SavedSceneRow key={scene.saved_result_id} scene={scene} />
          ))}
        </div>
        {hasMore && (
          <button
            type="button"
            className="upload-details-transcript-toggle"
            onClick={() => setVisibleSavedCount((v) => Math.min(v + SAVED_STEP_COUNT, savedScenes.length))}
          >
            <span>View More</span>
            <Icon name="chevron-down" size={13} />
          </button>
        )}
        {!hasMore && isExpanded && (
          <button
            type="button"
            className="upload-details-transcript-toggle"
            onClick={() => setVisibleSavedCount(SAVED_INITIAL_COUNT)}
          >
            <span>Show Less</span>
          </button>
        )}
      </>
    );
  }

  return (
    <div>
      <Link to={basePath} className="back-to-library">
        <Icon name="arrow-left" size={14} />
        Back to Library
      </Link>

      <div className="page-header-row">
        <div>
          <h1 className="page-title">
            Upload Details
            <img src={greenLeafImg} alt="" className="page-title-leaf" />
          </h1>
        </div>
      </div>

      <div className="upload-details-grid">
        <div className="upload-details-media">{renderMediaArea()}</div>

        <div className="upload-details-file ui-card ui-card--alt-bg">
          <h2 style={{ margin: "0 0 2px", fontSize: 18, fontFamily: "var(--font-extended)" }}>{video.title}</h2>
          <p className="text-muted" style={{ margin: "0 0 14px", fontSize: 12.5 }}>{video.original_filename}</p>

          <div className="upload-details-info-row">
            <span className="text-muted">Status</span>
            <StatusBadge status={video.status} label={STATUS_LABEL[video.status] ?? video.status} />
          </div>
          <div className="upload-details-info-row">
            <span className="text-muted">Type</span>
            <span>{video.media_type === "audio" ? "Audio" : "Video"}</span>
          </div>
          <div className="upload-details-info-row">
            <span className="text-muted">Size</span>
            <span>{formatBytes(video.file_size_bytes)}</span>
          </div>
          <div className="upload-details-info-row">
            <span className="text-muted">Duration</span>
            <span>{formatDuration(video.duration_seconds)}</span>
          </div>
          <div className="upload-details-info-row">
            <span className="text-muted">Uploaded</span>
            <span>{formatDate(video.uploaded_at)}</span>
          </div>
          <div className="upload-details-info-row upload-details-info-row--last">
            <span className="text-muted">Categories</span>
            <span>{video.categories.length > 0 ? video.categories.map((c) => c.name).join(", ") : "Uncategorized"}</span>
          </div>

          {video.status === "failed" && video.processing_error && (
            <p className="form-error" style={{ marginTop: 12 }}>{video.processing_error}</p>
          )}
        </div>

        <div className="upload-details-transcript ui-card ui-card--alt-bg">
          <h3 style={{ fontSize: 14, marginTop: 0 }}>Transcript</h3>
          {renderTranscript()}
        </div>

        <div className="upload-details-saved ui-card ui-card--alt-bg">
          <h3 style={{ fontSize: 14, marginTop: 0 }}>
            Saved Scenes{savedScenes != null ? ` (${savedScenes.length})` : ""}
          </h3>
          {renderSavedScenes()}
        </div>
      </div>
    </div>
  );
}
