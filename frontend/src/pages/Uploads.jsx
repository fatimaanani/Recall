import { useEffect, useState } from "react";
import "../styles/pages/Uploads.css";
import "../components/UploadDropzone.css";

import Icon from "../components/Icon";
import AssetPlaceholder from "../components/AssetPlaceholder";
import greenLeafImg from "../assets/decorations/greenLeaf-trimmed.png";
import uploadBrowseMascotImg from "../assets/mascots/uploadBrowseMascot-trimmed.png";
import processRowImg from "../assets/decorations/designAboveBrowse-trimmed.png";
import * as userService from "../services/userService";
import { useStagedUploadQueue, formatFileSize, MAX_STAGED_FILES } from "../hooks/useStagedUploadQueue";
import { UPLOAD_STATE_META } from "../mocks/mockData";

const QUEUE_ITEM_LABEL = {
  queued: "Queued",
  uploading: `${UPLOAD_STATE_META.uploading.label}...`,
  processing: `${UPLOAD_STATE_META.processing.label}...`,
  subtitles: `${UPLOAD_STATE_META.subtitles.label}...`,
  done: UPLOAD_STATE_META.done.label,
  error: "Failed",
};

const QUEUE_ITEM_PROGRESS_CLASS = {
  uploading: UPLOAD_STATE_META.uploading.className,
  processing: UPLOAD_STATE_META.processing.className,
  subtitles: UPLOAD_STATE_META.subtitles.className,
  done: UPLOAD_STATE_META.done.className,
  error: "upload-state-error",
};

// Upload Media page, dropzone + staged files + upload queue
export default function Uploads() {
  const [storageUsage, setStorageUsage] = useState(null);

  useEffect(() => {
    refreshStorageUsage();
  }, []);

  function refreshStorageUsage() {
    userService.getStorageUsage().then(setStorageUsage).catch(() => {});
  }

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
    attachSubtitleFile,
    removeSubtitleFile,
    handleConfirmUpload,
    dismissQueueItem,
  } = useStagedUploadQueue({ onUploadSuccess: refreshStorageUsage });

  const usedBytes = storageUsage?.used_bytes ?? 0;
  const limitBytes = storageUsage?.limit_bytes || 1;
  const usedLabel = formatFileSize(usedBytes);
  const limitLabel = formatFileSize(limitBytes);
  const usedPercent = storageUsage ? Math.min(100, Math.round((usedBytes / limitBytes) * 100)) : 0;

  return (
    <div>
      <div className="page-header uploads-header-row">
        <div>
          <h1 className="page-title">
            Upload Media
            <img src={greenLeafImg} alt="" className="page-title-leaf" />
          </h1>
          <p className="page-subtitle">
            Add your videos and audio to the archive.
            <br />
            We&apos;ll extract, process, and make them searchable.
          </p>
        </div>
        <img src={processRowImg} alt="Raw Media, Processing, Archived" className="uploads-process-illustration" />
      </div>

      <div className="uploads-layout">
        <div style={{ minWidth: 0 }}>
          <div
            className={`upload-dropzone upload-dropzone--mascot${isDragOver ? " upload-dropzone--drag-over" : ""}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <span className="dropzone-icon">
              <Icon name="cloud-upload" size={40} />
            </span>
            <p style={{ marginTop: 8, fontWeight: 500, fontFamily: "var(--font-extended)" }}>Drag &amp; drop your files here</p>
            <p className="text-muted">or</p>
            <label className="btn btn--browse" style={{ cursor: "pointer" }}>
              <Icon name="folder" size={16} />
              <span>Browse Files</span>
              <input
                type="file"
                accept=".mp4,.mov,.mkv,.webm,.mp3,.wav,.flac,.m4a"
                multiple
                onChange={handleFileChange}
                style={{ display: "none" }}
              />
            </label>
            <p className="upload-dropzone__hint">
              Supports: MP4, MOV, MKV, WEBM, MP3, WAV, FLAC, M4A
              <br />
              Max file size: 5 GB &middot; Up to {MAX_STAGED_FILES} files at a time
            </p>
            <img src={uploadBrowseMascotImg} alt="" className="upload-mascot" />
          </div>

          {(stagedFiles.length > 0 || stagingError) && (
            <div className="ui-card staged-files-card">
              <div className="page-header-row" style={{ marginBottom: 8 }}>
                <h3 style={{ fontSize: 15 }}>Selected Files ({stagedFiles.length})</h3>
                <button
                  type="button"
                  className="btn btn--upload-confirm btn--sm"
                  disabled={stagedFiles.length === 0}
                  onClick={handleConfirmUpload}
                >
                  <Icon name="check" size={14} />
                  <span>Upload</span>
                </button>
              </div>

              {stagedFiles.map((staged) => (
                <div key={staged.stagedId} className="staged-file-row">
                  <div className="staged-file-details">
                    <p className="staged-file-name">{staged.fileName}</p>
                    <p className="staged-file-meta">{staged.sizeLabel}</p>
                    {staged.subtitleFile ? (
                      <p className="staged-file-subtitle">
                        <Icon name="file-text" size={12} style={{ verticalAlign: "-1px" }} />
                        {" "}
                        {staged.subtitleFile.name}
                        <button
                          type="button"
                          className="staged-file-subtitle-remove"
                          aria-label={`Remove subtitle for ${staged.fileName}`}
                          onClick={() => removeSubtitleFile(staged.stagedId)}
                        >
                          <Icon name="x" size={11} />
                        </button>
                      </p>
                    ) : (
                      <label className="staged-file-subtitle-attach">
                        <Icon name="file-text" size={12} style={{ verticalAlign: "-1px" }} />
                        {" "}Attach subtitle (.srt, .vtt)
                        <input
                          type="file"
                          accept=".srt,.vtt"
                          style={{ display: "none" }}
                          onChange={(event) => {
                            const file = event.target.files?.[0];
                            if (file) attachSubtitleFile(staged.stagedId, file);
                            event.target.value = "";
                          }}
                        />
                      </label>
                    )}
                  </div>
                  <button
                    type="button"
                    className="staged-file-remove"
                    aria-label={`Remove ${staged.fileName}`}
                    onClick={() => removeStagedFile(staged.stagedId)}
                  >
                    <Icon name="x" size={16} />
                  </button>
                </div>
              ))}

              {stagingError && <p className="staging-error">{stagingError}</p>}
            </div>
          )}

          <div className="ui-card">
            <div className="page-header-row" style={{ marginBottom: 8 }}>
              <h3 style={{ fontSize: 15 }}>Upload Queue ({queue.length})</h3>
            </div>

            {queue.length === 0 ? (
              <p className="text-muted" style={{ padding: "var(--space-md) 0" }}>
                Nothing uploaded yet this session.
              </p>
            ) : (
              queue.map((item) => (
                <div key={item.id} className="item-row">
                  <AssetPlaceholder path="assets/thumbnails/pending.png" width={48} height={48} className="item-thumb" />

                  <div className="item-details">
                    <p className="item-name">{item.fileName}</p>
                    <p className="item-meta">{item.sizeLabel}</p>
                  </div>

                  <div className="item-progress">
                    <div className="item-progress-head">
                      <p className="item-status">{QUEUE_ITEM_LABEL[item.state] ?? item.state}</p>
                      <span className="item-percent">
                        {item.state === "queued" || item.state === "error" ? "--" : `${item.progressPercent}%`}
                      </span>
                    </div>
                    <div className="progress-bar">
                      <div
                        className={`progress-bar__fill ${QUEUE_ITEM_PROGRESS_CLASS[item.state] ?? "upload-state-uploading"}`}
                        style={{ width: `${item.state === "error" ? 100 : item.state === "queued" ? 0 : item.progressPercent}%` }}
                      />
                    </div>
                    {item.state === "error" && (
                      <p className="item-stage" style={{ color: "var(--color-danger)" }}>{item.errorMessage}</p>
                    )}
                  </div>

                  <div className="item-action">
                    {item.state === "done" && <Icon name="check" size={18} style={{ color: "var(--color-success)" }} />}
                    {item.state === "error" && (
                      <button
                        type="button"
                        className="item-dismiss"
                        aria-label={`Dismiss ${item.fileName}`}
                        onClick={() => dismissQueueItem(item.id)}
                      >
                        <Icon name="x" size={18} />
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="process-row">
            <div className="process-title-row">
              <span className="process-lead-icon">
                <Icon name="search" size={18} />
              </span>
              <h3 className="process-title" style={{ fontSize: 15 }}>What happens after upload?</h3>
            </div>
            <div className="process-chain">
              <div className="process-step">
                <span className="process-step-icon process-step-icon-extract"><Icon name="waveform" size={22} /></span>
                <div>
                  <strong style={{ fontSize: 13 }}>Extract Audio</strong>
                  <p className="text-muted">We extract the audio from your file.</p>
                </div>
              </div>
              <Icon name="arrow-right" size={16} className="process-arrow" />
              <div className="process-step">
                <span className="process-step-icon process-step-icon-subtitles"><Icon name="file-text" size={22} /></span>
                <div>
                  <strong style={{ fontSize: 13 }}>Generate / Read Subtitles</strong>
                  <p className="text-muted">We create or read subtitles.</p>
                </div>
              </div>
              <Icon name="arrow-right" size={16} className="process-arrow" />
              <div className="process-step">
                <span className="process-step-icon process-step-icon-index"><Icon name="file-text" size={22} /></span>
                <div>
                  <strong style={{ fontSize: 13 }}>Index Content</strong>
                  <p className="text-muted">The content is indexed for fast searching.</p>
                </div>
              </div>
              <Icon name="arrow-right" size={16} className="process-arrow" />
              <div className="process-step">
                <span className="process-step-icon process-step-icon-library"><Icon name="books" size={22} /></span>
                <div>
                  <strong style={{ fontSize: 13 }}>Add to Library</strong>
                  <p className="text-muted">Your file is archived and ready to go!</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div>
          <div className="ui-card sidebar-card">
            <h3 style={{ fontSize: 15 }}>
              <Icon name="film" size={16} style={{ marginRight: 6, verticalAlign: "-2px" }} />
              Upload Guide
            </h3>
            <div className="guide-list">
              <div className="guide-step">
                <span className="guide-step-icon">1.</span>
                <div>
                  <strong>Upload</strong>
                  <p>Add your video or audio files.</p>
                </div>
              </div>
              <div className="guide-step">
                <span className="guide-step-icon">2.</span>
                <div>
                  <strong>Process</strong>
                  <p>We&apos;ll extract audio, generate subtitles (if needed), and index the content.</p>
                </div>
              </div>
              <div className="guide-step">
                <span className="guide-step-icon">3.</span>
                <div>
                  <strong>Archive</strong>
                  <p>Your media will be added to the library and ready to search.</p>
                </div>
              </div>
            </div>
          </div>

          <div className="ui-card better-results-notice">
            <span className="better-results-notice__icon">
              <Icon name="lightbulb" size={16} />
            </span>
            <p>
              Better results come from high quality audio and clear content.{" "}
              <Icon name="heart" size={12} className="heart-accent" style={{ display: "inline", verticalAlign: "-1px" }} />
            </p>
          </div>

          <div className="ui-card sidebar-card">
            <h3 style={{ fontSize: 15 }}>Storage Usage</h3>
            <div className="storage-usage-row">
              <div className="storage-ring" style={{ "--pct": usedPercent }}>
                <span>{usedPercent}%</span>
              </div>
              <p style={{ margin: 0, fontWeight: 500, fontFamily: "var(--font-extended)" }}>{usedLabel} / {limitLabel} used</p>
            </div>
          </div>

          <div className="ui-card sidebar-card">
            <h3 style={{ fontSize: 15 }}>Tips</h3>
            <ul className="tips-list">
              <li>Videos with subtitles give better results.</li>
              <li>You can upload subtitle files (SRT, VTT) to improve accuracy.</li>
              <li>Large files may take a while to process.</li>
            </ul>
            <p style={{ marginTop: 12, fontSize: 12.5 }}>
              Need help? <a href="#docs" className="link-accent">View documentation</a>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
