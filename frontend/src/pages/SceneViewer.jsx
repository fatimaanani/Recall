import { useEffect, useState } from "react";
import { useParams, useLocation, Link } from "react-router-dom";
import "../styles/pages/SceneViewer.css";

import Icon from "../components/Icon";
import { MethodBadge } from "../components/Badge";
import { useProtectedMedia } from "../hooks/useProtectedMedia";
import * as clipService from "../services/clipService";
import * as resultService from "../services/resultService";
import { getErrorMessage } from "../services/apiClient";
import { SEARCH_METHOD_META } from "../mocks/mockData";
import greenLeafImg from "../assets/decorations/greenLeaf-trimmed.png";
import flowerBranchImg from "../assets/decorations/flowerBranch-trimmed.png";
import branchImg from "../assets/decorations/branch-trimmed.png";
import bestMatchMascotImg from "../assets/mascots/bestMatchMascot.svg";

const SCORE_RING_COLOR = {
  exact_text: "var(--method-text)",
  semantic: "var(--method-semantic)",
  speech_to_text: "var(--method-speech)",
};

// Positive integers only ("0", "-3", "undefined", "null", "" all fail).
const VALID_RESULT_ID_PATTERN = /^[1-9]\d*$/;

// "Back to Results" only makes sense if this page was actually reached from a real Results -> View Scene flow; otherwise Go to Search is the more honest next step.
function BackNav({ hasResultsFlow }) {
  return hasResultsFlow ? (
    <Link to="/home/results" className="back-to-settings">
      <Icon name="arrow-left" size={14} />
      Back to Results
    </Link>
  ) : (
    <Link to="/search" className="back-to-settings">
      <Icon name="arrow-left" size={14} />
      Go to Search
    </Link>
  );
}

// Built only from fields the backend actually returns; never an AI-generated sentence, missing evidence is just left out.
function buildWhyThisMatched({ matchedText, queryText, searchMethod, confidenceScore, keywordScore, semanticScore }) {
  const methodLabel = SEARCH_METHOD_META[searchMethod]?.label ?? searchMethod;
  const percent = Math.round(confidenceScore * 100);
  const parts = [];

  parts.push(
    queryText
      ? `This scene was selected for your search "${queryText}" using ${methodLabel}, with a ${percent}% confidence score.`
      : `This scene was selected using ${methodLabel}, with a ${percent}% confidence score.`
  );

  if (matchedText) {
    parts.push(`Matched transcript: "${matchedText}"`);
  }

  if (keywordScore != null && semanticScore != null) {
    parts.push(
      `Both a keyword match (${Math.round(keywordScore * 100)}%) and a semantic match (${Math.round(semanticScore * 100)}%) contributed to this result.`
    );
  }

  return parts.join(" ");
}

export default function SceneViewer() {
  const { resultId } = useParams();
  const location = useLocation();
  // Route state only ever arrives via a result card's "View Scene" link; used only for Back-nav wording, never for data.
  const hasResultsFlow = location.state != null;
  const isValidResultId = VALID_RESULT_ID_PATTERN.test(resultId ?? "");

  const [clip, setClip] = useState(null);
  const [isGenerating, setIsGenerating] = useState(isValidResultId);
  const [generateError, setGenerateError] = useState("");

  const [resultDetail, setResultDetail] = useState(null);
  const [isLoadingResultDetail, setIsLoadingResultDetail] = useState(isValidResultId);
  const [resultDetailError, setResultDetailError] = useState("");

  // Gates only the Summary/Key Points cards, never the clip player; goes false once the post-clip enrichment re-fetch below settles.
  const [isEnrichmentPending, setIsEnrichmentPending] = useState(isValidResultId);

  const [isSaved, setIsSaved] = useState(false);
  const [isSavingBookmark, setIsSavingBookmark] = useState(false);
  const [bookmarkError, setBookmarkError] = useState("");

  useEffect(() => {
    if (!isValidResultId) {
      setIsGenerating(false);
      setClip(null);
      setGenerateError("");
      return;
    }

    // A real AbortController (not just a `cancelled` boolean) so React 18 StrictMode's double-invoked mount effect can't leave a duplicate POST /api/results/{id}/clip in flight.
    const controller = new AbortController();
    setIsGenerating(true);
    setGenerateError("");
    setClip(null);

    clipService
      .generateClip(resultId, { signal: controller.signal })
      .then((result) => {
        setClip(result);
      })
      .catch((err) => {
        if (err.name === "CanceledError" || err.code === "ERR_CANCELED") return;
        setGenerateError(getErrorMessage(err, "Couldn't load this scene. Please try again."));
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsGenerating(false);
      });

    return () => {
      controller.abort();
    };
  }, [resultId, isValidResultId]);

  // Fetched independently of (and in parallel with) clip generation above; both must succeed before the main content renders.
  useEffect(() => {
    if (!isValidResultId) {
      setIsLoadingResultDetail(false);
      setResultDetail(null);
      setResultDetailError("");
      return undefined;
    }

    const controller = new AbortController();
    setIsLoadingResultDetail(true);
    setResultDetailError("");

    resultService
      .getResult(resultId, { signal: controller.signal })
      .then((detail) => {
        setResultDetail(detail);
        setIsSaved(detail.is_saved);
      })
      .catch((err) => {
        if (err.name === "CanceledError" || err.code === "ERR_CANCELED") return;
        setResultDetailError(getErrorMessage(err, "Couldn't load this scene. Please try again."));
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoadingResultDetail(false);
      });

    return () => {
      controller.abort();
    };
  }, [resultId, isValidResultId]);

  // Runs once clip generation/reuse succeeds: the initial result-detail GET above can run before the clip exists, so summary/key_points are honestly null until this re-fetch. Deliberately doesn't touch isSaved, so it can't clobber a bookmark toggle made in between the two GETs.
  useEffect(() => {
    if (!isValidResultId || !clip) {
      return undefined;
    }

    const controller = new AbortController();
    setIsEnrichmentPending(true);

    resultService
      .getResult(resultId, { signal: controller.signal })
      .then((detail) => {
        setResultDetail(detail);
      })
      .catch((err) => {
        if (err.name === "CanceledError" || err.code === "ERR_CANCELED") return;
        // Not fatal -- resultDetail already has whatever the first GET returned.
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsEnrichmentPending(false);
      });

    return () => {
      controller.abort();
    };
  }, [clip, resultId, isValidResultId]);

  const { url: mediaUrl, isLoading: isMediaLoading, error: mediaError } = useProtectedMedia(clip?.clip_stream_url ?? null);

  // Disabled while a request is in flight so a rapid double-click can't fire two overlapping save/unsave calls.
  function handleToggleBookmark() {
    if (isSavingBookmark) return;
    setIsSavingBookmark(true);
    setBookmarkError("");
    const action = isSaved ? resultService.unsaveResult(resultId) : resultService.saveResult(resultId);
    action
      .then(() => setIsSaved((v) => !v))
      .catch((err) => setBookmarkError(getErrorMessage(err, "Couldn't update saved scenes. Please try again.")))
      .finally(() => setIsSavingBookmark(false));
  }

  if (!isValidResultId) {
    return (
      <div style={{ textAlign: "center", padding: "64px 16px" }}>
        <p style={{ fontWeight: 500, fontFamily: "var(--font-extended)", fontSize: 16 }}>
          We couldn't find this scene.
        </p>
        <p className="text-muted">
          Scene Viewer opens from a search result -- start a new search to select one.
        </p>
        <Link to="/search" className="btn btn--primary" style={{ display: "inline-flex", marginTop: 12 }}>
          <Icon name="search" size={16} />
          <span>Go to Search</span>
        </Link>
      </div>
    );
  }

  if (isGenerating || isLoadingResultDetail) {
    return (
      <div>
        <BackNav hasResultsFlow={hasResultsFlow} />
        <p className="text-muted">Loading this scene...</p>
      </div>
    );
  }

  if (generateError || resultDetailError || !clip || !resultDetail) {
    return (
      <div>
        <BackNav hasResultsFlow={hasResultsFlow} />
        <p className="form-error">{generateError || resultDetailError || "This scene couldn't be loaded."}</p>
      </div>
    );
  }

  const topic = resultDetail.categories.length > 0 ? resultDetail.categories.map((c) => c.name).join(", ") : "Uncategorized";
  const whyThisMatched = buildWhyThisMatched({
    matchedText: clip.matched_text,
    queryText: resultDetail.query_text,
    searchMethod: clip.search_method,
    confidenceScore: clip.confidence_score,
    keywordScore: resultDetail.keyword_score,
    semanticScore: resultDetail.semantic_score,
  });

  return (
    <div>
      <BackNav hasResultsFlow={hasResultsFlow} />

      <div className="page-header">
        <h1 className="page-title">
          Scene Viewer
          <img src={greenLeafImg} alt="" className="page-title-leaf" />
        </h1>
      </div>

      <div className="found-banner">
        {/* No dark-mode variant for this asset, so unlike the sidebar tips there's no light/dark swap here. */}
        <span className="found-banner__mascot">
          <img src={bestMatchMascotImg} alt="" />
        </span>
        <div>
          <strong>Best match found!</strong>
          {clip.matched_text && <p style={{ margin: 0 }}>We jumped to the part where &ldquo;{clip.matched_text}&rdquo; is explained.</p>}
        </div>
      </div>

      <div className="viewer-grid">
        <div>
          <div className="player">
            {mediaError ? (
              <p style={{ color: "#fff", padding: 16, textAlign: "center" }}>
                Couldn't load this clip. {getErrorMessage(mediaError, "Please try again.")}
              </p>
            ) : isMediaLoading || !mediaUrl ? (
              <p style={{ color: "#fff" }}>Loading clip...</p>
            ) : clip.is_audio_only ? (
              <audio src={mediaUrl} controls style={{ width: "90%" }} />
            ) : (
              <video src={mediaUrl} controls style={{ width: "100%", height: "100%", objectFit: "contain" }} />
            )}
          </div>

          <div className="ui-card ui-card--alt-bg" style={{ marginTop: 16 }}>
            <div className="scene-insight-grid">
              <div>
                <h3 style={{ fontSize: 14 }}>Summary</h3>
                {/* Deterministic, transcript-grounded excerpt, not AI-generated. */}
                {isEnrichmentPending ? (
                  <p className="text-muted" style={{ margin: 0, fontSize: 13.5 }}>Preparing scene details...</p>
                ) : (
                  <p style={{ margin: 0, fontSize: 13.5 }}>
                    {resultDetail.summary || "No summary available for this scene."}
                  </p>
                )}
              </div>
              <div>
                <h3 style={{ fontSize: 14 }}>Why this matched?</h3>
                <p style={{ margin: 0, fontSize: 13.5 }}>{whyThisMatched}</p>
              </div>
            </div>
          </div>
        </div>

        <div className="sidebar-panel">
          <div className="ui-card ui-card--alt-bg" style={{ position: "relative" }}>
            <div className="scene-meta-card__actions">
              <button
                type="button"
                className={isSaved ? "scene-meta-card__actions--saved" : ""}
                disabled={isSavingBookmark}
                onClick={handleToggleBookmark}
                title={isSaved ? "Remove from saved scenes" : "Save this scene"}
              >
                <Icon name="bookmark" size={18} style={isSaved ? { fill: "currentColor" } : undefined} />
              </button>
            </div>
            {bookmarkError && (
              <p className="form-error" style={{ position: "absolute", top: 46, right: 12, fontSize: 11, margin: 0, maxWidth: 140, textAlign: "right" }}>
                {bookmarkError}
              </p>
            )}
            <h3 style={{ fontSize: 14 }}>{clip.video_title}</h3>
            <p className="text-muted" style={{ marginBottom: 4 }}>Topic</p>
            <p style={{ fontWeight: 500, fontFamily: "var(--font-extended)" }}>{topic}</p>
            <p className="text-muted" style={{ marginBottom: 4 }}>Episode / Lecture</p>
            <p style={{ fontWeight: 500, fontFamily: "var(--font-extended)" }}>{clip.video_title}</p>
            <p className="text-muted" style={{ marginBottom: 4 }}>Timestamp (Matched)</p>
            <p style={{ fontWeight: 500, fontFamily: "var(--font-extended)" }}>
              {formatSeconds(clip.start_time)} - {formatSeconds(clip.end_time)}
            </p>
          </div>

          <div className="ui-card ui-card--alt-bg">
            <p className="text-muted" style={{ marginBottom: 4 }}>Search Method</p>
            <MethodBadge method={clip.search_method} />
            <p className="text-muted" style={{ margin: "10px 0 4px" }}>Source</p>
            <p style={{ fontSize: 13 }}>{clip.video_title}</p>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12 }}>
              <div
                className="match-score-ring"
                style={{ background: "var(--color-surface)", color: "var(--color-text-primary)", border: `3px solid ${SCORE_RING_COLOR[clip.search_method] ?? "var(--color-border-strong)"}` }}
              >
                {Math.round(clip.confidence_score * 100)}%
              </div>
              <p className="text-muted" style={{ margin: 0 }}>Match Score</p>
            </div>
          </div>

          <div className="ui-card ui-card--alt-bg">
            <h3 style={{ fontSize: 14 }}>Key Points in this Segment</h3>
            {/* Up to 5 deduplicated, non-filler sentences from the transcript span, in spoken order. Never invented. */}
            {isEnrichmentPending ? (
              <p className="text-muted" style={{ margin: 0 }}>Preparing scene details...</p>
            ) : resultDetail.key_points.length > 0 ? (
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13.5, display: "flex", flexDirection: "column", gap: 6 }}>
                {resultDetail.key_points.map((point, i) => (
                  <li key={i}>{point}</li>
                ))}
              </ul>
            ) : (
              <p className="text-muted" style={{ margin: 0 }}>No key points available for this clip.</p>
            )}
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

function formatSeconds(seconds) {
  if (seconds == null) return "--:--";
  const total = Math.round(seconds);
  const mins = Math.floor(total / 60);
  const secs = total % 60;
  return `${mins}:${String(secs).padStart(2, "0")}`;
}
