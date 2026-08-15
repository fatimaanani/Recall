import { useEffect, useRef, useState } from "react";

import * as videoService from "../services/videoService";
import { getErrorMessage } from "../services/apiClient";
import { useAuth } from "../context/AuthContext";

export const MAX_STAGED_FILES = 6;
// Mirrors backend max_upload_size_bytes, client-side early check only
export const MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024 * 1024;
export const CONCURRENCY_LIMIT = 2;
const AUTO_REMOVE_DELAY_MS = 1200;

// Status poll interval, once upload request itself has finished
const STATUS_POLL_INTERVAL_MS = 2500;

// Fixed stage-progress milestones, not real percentages
const STAGE_MILESTONE_PERCENT = {
  processing: 50,
  subtitles: 80,
  done: 100,
};

function mapVideoToQueueState(video) {
  if (video.status === "ready") return "done";
  if (video.status === "failed") return "error";
  return video.current_stage === "whisper_transcription" ? "subtitles" : "processing";
}

// Processing error text, collapsed + capped for display
const MAX_ERROR_DISPLAY_LENGTH = 140;

function formatProcessingError(message) {
  if (!message) return "Processing failed.";
  const singleLine = message.replace(/\s+/g, " ").trim();
  if (singleLine.length <= MAX_ERROR_DISPLAY_LENGTH) return singleLine;
  return `${singleLine.slice(0, MAX_ERROR_DISPLAY_LENGTH - 1)}…`;
}

function titleFromFilename(fileName) {
  const dotIndex = fileName.lastIndexOf(".");
  return dotIndex > 0 ? fileName.slice(0, dotIndex) : fileName;
}

export function formatFileSize(bytes) {
  if (bytes >= 1_000_000_000) return `${(bytes / 1_000_000_000).toFixed(2)} GB`;
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  if (bytes > 0) return `${Math.max(1, Math.round(bytes / 1000))} KB`;
  return "0 KB";
}

// Client-side-only ids, not sent to the backend
let nextStagedId = 1;
let nextQueueId = 1;

export function useStagedUploadQueue({ onUploadSuccess } = {}) {
  const { currentUser } = useAuth();
  const [stagedFiles, setStagedFiles] = useState([]);
  const [stagingError, setStagingError] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);
  const [queue, setQueue] = useState([]);
  // Guards mount-restore effect, seeds queue once per mount
  const hasRestoredQueueRef = useRef(false);

  // Concurrency bookkeeping, plain refs (no re-render needed)
  const pendingFilesRef = useRef([]);
  const activeCountRef = useRef(0);
  // queueId -> setTimeout id, "done" item auto-remove timers
  const removalTimeoutsRef = useRef(new Map());
  // queueId -> setInterval id, per-item status polling
  const statusPollingRef = useRef(new Map());

  useEffect(() => {
    return () => {
      removalTimeoutsRef.current.forEach((timeoutId) => clearTimeout(timeoutId));
      removalTimeoutsRef.current.clear();
      statusPollingRef.current.forEach((intervalId) => clearInterval(intervalId));
      statusPollingRef.current.clear();
    };
  }, []);

  // Restore in-progress uploads into the queue, once on mount
  useEffect(() => {
    if (!currentUser || hasRestoredQueueRef.current) return;
    hasRestoredQueueRef.current = true;

    videoService
      .listVideos()
      .then((videos) => {
        const inProgress = videos.filter(
          (video) =>
            video.owner_id === currentUser.id &&
            (video.status === "uploaded" || video.status === "processing")
        );
        if (inProgress.length === 0) return;

        const restoredItems = [];
        const pollTargets = [];
        for (const video of inProgress) {
          const queueId = nextQueueId++;
          const state = mapVideoToQueueState(video);
          restoredItems.push({
            id: queueId,
            fileName: video.original_filename,
            sizeLabel: formatFileSize(video.file_size_bytes),
            progressPercent: STAGE_MILESTONE_PERCENT[state] ?? 0,
            state,
            errorMessage: null,
          });
          pollTargets.push({ queueId, videoId: video.id });
        }

        setQueue((prev) => [...restoredItems, ...prev]);
        pollTargets.forEach(({ queueId, videoId }) => startStatusPolling(queueId, videoId));
      })
      .catch(() => {
        // Failed restore, queue just misses these items this session
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentUser]);

  function scheduleAutoRemove(queueId) {
    const timeoutId = setTimeout(() => {
      setQueue((prev) => prev.filter((item) => item.id !== queueId));
      removalTimeoutsRef.current.delete(queueId);
    }, AUTO_REMOVE_DELAY_MS);
    removalTimeoutsRef.current.set(queueId, timeoutId);
  }

  function stopStatusPolling(queueId) {
    const intervalId = statusPollingRef.current.get(queueId);
    if (intervalId) {
      clearInterval(intervalId);
      statusPollingRef.current.delete(queueId);
    }
  }

  function startStatusPolling(queueId, videoId) {
    stopStatusPolling(queueId);
    const intervalId = setInterval(() => {
      videoService
        .getVideo(videoId)
        .then((video) => {
          const nextState = mapVideoToQueueState(video);
          setQueue((prev) =>
            prev.map((item) =>
              item.id === queueId
                ? {
                    ...item,
                    state: nextState,
                    // "error" preserves last known percent, not overwritten
                    progressPercent: STAGE_MILESTONE_PERCENT[nextState] ?? item.progressPercent,
                    errorMessage: nextState === "error" ? formatProcessingError(video.processing_error) : item.errorMessage,
                  }
                : item
            )
          );
          if (nextState === "done") {
            stopStatusPolling(queueId);
            scheduleAutoRemove(queueId);
          } else if (nextState === "error") {
            stopStatusPolling(queueId);
          }
        })
        .catch(() => {
          // Transient fetch error, stop polling rather than spin forever
          stopStatusPolling(queueId);
        });
    }, STATUS_POLL_INTERVAL_MS);
    statusPollingRef.current.set(queueId, intervalId);
  }

  function pumpQueue() {
    while (activeCountRef.current < CONCURRENCY_LIMIT && pendingFilesRef.current.length > 0) {
      const next = pendingFilesRef.current.shift();
      activeCountRef.current += 1;
      beginUpload(next.queueId, next.file, next.subtitleFile);
    }
  }

  // subtitleFile is optional (a matching SRT/VTT attached before confirming upload), sent as one extra multipart field.
  function beginUpload(queueId, file, subtitleFile) {
    setQueue((prev) =>
      prev.map((item) => (item.id === queueId ? { ...item, state: "uploading" } : item))
    );

    const formData = new FormData();
    formData.append("title", titleFromFilename(file.name));
    formData.append("file", file);
    if (subtitleFile) {
      formData.append("subtitle_file", subtitleFile);
    }

    videoService
      .uploadVideo(formData, (progressEvent) => {
        const percent = progressEvent.total
          ? Math.round((progressEvent.loaded / progressEvent.total) * 100)
          : 0;
        setQueue((prev) =>
          prev.map((item) => (item.id === queueId ? { ...item, progressPercent: percent } : item))
        );
      })
      .then((video) => {
        // Upload request resolved; progress now moves via stage milestones only.
        const nextState = mapVideoToQueueState(video);
        setQueue((prev) =>
          prev.map((item) =>
            item.id === queueId
              ? {
                  ...item,
                  state: nextState,
                  progressPercent: STAGE_MILESTONE_PERCENT[nextState] ?? item.progressPercent,
                  errorMessage: nextState === "error" ? formatProcessingError(video.processing_error) : item.errorMessage,
                }
              : item
          )
        );
        onUploadSuccess?.();
        if (nextState === "done") {
          scheduleAutoRemove(queueId);
        } else if (nextState !== "error") {
          startStatusPolling(queueId, video.id);
        }
      })
      .catch((err) => {
        // 409 duplicate, 415 unsupported type, 413 too large/over quota
        const message = getErrorMessage(err, "Upload failed. Please try again.");
        setQueue((prev) =>
          prev.map((item) =>
            item.id === queueId ? { ...item, state: "error", errorMessage: message } : item
          )
        );
      })
      .finally(() => {
        activeCountRef.current -= 1;
        pumpQueue();
      });
  }

  // No network request yet, just staging
  function stageFiles(fileList) {
    const incoming = Array.from(fileList);
    if (incoming.length === 0) return;

    setStagedFiles((prev) => {
      const next = [...prev];
      let error = "";

      for (const file of incoming) {
        if (next.length >= MAX_STAGED_FILES) {
          error = `You can stage up to ${MAX_STAGED_FILES} files at a time.`;
          break;
        }
        const isDuplicate = next.some(
          (staged) =>
            staged.file.name === file.name &&
            staged.file.size === file.size &&
            staged.file.lastModified === file.lastModified
        );
        if (isDuplicate) continue;
        if (file.size > MAX_FILE_SIZE_BYTES) {
          error = `"${file.name}" is larger than the 5 GB per-file limit and wasn't added.`;
          continue;
        }
        next.push({
          stagedId: nextStagedId++,
          file,
          fileName: file.name,
          sizeLabel: formatFileSize(file.size),
          // Optional matching subtitle file, attached later via attachSubtitleFile.
          subtitleFile: null,
        });
      }

      setStagingError(error);
      return next;
    });
  }

  // Client-side extension check only, real validation happens server-side in subtitle_validation.py.
  function attachSubtitleFile(stagedId, subtitleFile) {
    const extension = subtitleFile.name.split(".").pop()?.toLowerCase();
    if (extension !== "srt" && extension !== "vtt") {
      setStagingError(`"${subtitleFile.name}" isn't a .srt or .vtt file.`);
      return;
    }
    setStagingError("");
    setStagedFiles((prev) =>
      prev.map((staged) => (staged.stagedId === stagedId ? { ...staged, subtitleFile } : staged))
    );
  }

  function removeSubtitleFile(stagedId) {
    setStagedFiles((prev) =>
      prev.map((staged) => (staged.stagedId === stagedId ? { ...staged, subtitleFile: null } : staged))
    );
  }

  function handleFileChange(event) {
    stageFiles(event.target.files);
    // Reset input so re-selecting the same file still fires onChange.
    event.target.value = "";
  }

  function handleDragOver(event) {
    event.preventDefault();
    setIsDragOver(true);
  }

  function handleDragLeave(event) {
    event.preventDefault();
    setIsDragOver(false);
  }

  function handleDrop(event) {
    event.preventDefault();
    setIsDragOver(false);
    stageFiles(event.dataTransfer.files);
  }

  function removeStagedFile(stagedId) {
    setStagedFiles((prev) => prev.filter((f) => f.stagedId !== stagedId));
    setStagingError("");
  }

  function handleConfirmUpload() {
    if (stagedFiles.length === 0) return;

    const newItems = stagedFiles.map(({ file, subtitleFile }) => {
      const queueId = nextQueueId++;
      pendingFilesRef.current.push({ queueId, file, subtitleFile });
      return {
        id: queueId,
        fileName: file.name,
        sizeLabel: formatFileSize(file.size),
        progressPercent: 0,
        state: "queued",
        errorMessage: null,
      };
    });

    setQueue((prev) => [...newItems, ...prev]);
    setStagedFiles([]);
    setStagingError("");
    pumpQueue();
  }

  // Only "error" items are dismissible
  function dismissQueueItem(queueId) {
    stopStatusPolling(queueId);
    setQueue((prev) => prev.filter((item) => item.id !== queueId));
  }

  return {
    stagedFiles,
    stagingError,
    isDragOver,
    queue,
    stageFiles,
    handleFileChange,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    removeStagedFile,
    attachSubtitleFile,
    removeSubtitleFile,
    handleConfirmUpload,
    dismissQueueItem,
  };
}
