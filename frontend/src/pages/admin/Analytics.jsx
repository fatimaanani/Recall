import { useEffect, useState } from "react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  LineChart, Line, PieChart, Pie, Cell, LabelList,
} from "recharts";
// Tooltip is still imported: only ResponseTimeChart uses it.

import Icon from "../../components/Icon";
import StatCard from "../../components/StatCard";
import "../../styles/pages/admin/Analytics.css";
import greenLeafImg from "../../assets/decorations/greenLeaf-trimmed.png";
import { getErrorMessage } from "../../services/apiClient";
import * as analyticsService from "../../services/analyticsService";
import * as videoService from "../../services/videoService";

const SEARCH_TYPE_COLOR = {
  exact_text: "var(--method-text)",
  semantic: "var(--method-semantic)",
  speech_to_text: "var(--method-speech)",
};
const SEARCH_TYPE_LABEL = {
  exact_text: "Exact Text Search",
  semantic: "Semantic Search",
  speech_to_text: "Speech-to-Text",
};

const TROPHIES = [
  { icon: "award", label: "Best Performing Method", key: "best_performing_method", noteKey: "best_performing_note", iconClass: "trophy-icon--best" },
  { icon: "target", label: "Highest Accuracy", key: "highest_accuracy_method", noteKey: "highest_accuracy_note", iconClass: "trophy-icon--accuracy" },
  { icon: "zap", label: "Fastest Method", key: "fastest_method", noteKey: "fastest_note", iconClass: "trophy-icon--fastest" },
];

const KPI_INFO_TEXT = {
  searchAccuracy: "Percentage of evaluated test cases where the expected scene was retrieved correctly.",
  averageResponseTime: "Average time required to complete real user searches during the selected period.",
  mediaFilesIndexed: "Number of ready media files processed and available to ReCall's live search pipeline.",
  queriesProcessed: "Total number of search queries submitted during the selected period.",
};

function formatMs(ms) {
  if (ms == null) return "--";
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} sec` : `${Math.round(ms)} ms`;
}

function msToSeconds(ms) {
  return ms / 1000;
}

// Backend date fields are plain "YYYY-MM-DD" strings, parsed with an explicit local midnight rather than passed bare to `new Date()` (which JS treats as UTC and can render one day off).
function formatShortDate(dateStr) {
  if (!dateStr) return "";
  const date = new Date(`${dateStr}T00:00:00`);
  if (Number.isNaN(date.getTime())) return dateStr;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function deltaLabelFor(kpi, unitFormatter = (v) => v, comparisonSuffix = "vs previous period") {
  if (!kpi || kpi.delta_percent == null) return null;
  const sign = kpi.delta_percent > 0 ? "+" : "";
  return `${sign}${kpi.delta_percent}% ${comparisonSuffix}`;
}

// Visual-only preview data, never sent to/from the backend and only ever rendered behind a "Preview data" badge until real evaluation data exists.
const PREVIEW_METHOD_PERFORMANCE = [
  { search_type: "exact_text", accuracy: 0.82, precision: 0.78, recall: 0.74 },
  { search_type: "semantic", accuracy: 0.88, precision: 0.81, recall: 0.85 },
  { search_type: "speech_to_text", accuracy: 0.71, precision: 0.69, recall: 0.66 },
];
const PREVIEW_EVALUATION_SUMMARY = {
  best_performing_method: "semantic",
  best_performing_note: "Highest F1 score for the postgresql backend this period.",
  highest_accuracy_method: "semantic",
  highest_accuracy_note: "Highest measured accuracy for the postgresql backend this period.",
  fastest_method: "exact_text",
  fastest_note: "Lowest average evaluation response time this period.",
};

// Search Method Performance Comparison -- grouped horizontal bars
function MethodComparisonChart({ evaluation }) {
  const hasRealData = evaluation.backend_available && evaluation.method_rows.length > 0;
  const emptyReason = !evaluation.backend_available
    ? evaluation.unavailable_reason
    : evaluation.unavailable_reason || "Evaluation has not been run yet.";

  const sourceRows = hasRealData ? evaluation.method_rows : PREVIEW_METHOD_PERFORMANCE;
  const data = sourceRows.map((row) => ({
    method: SEARCH_TYPE_LABEL[row.search_type],
    Accuracy: Math.round((row.accuracy ?? 0) * 100),
    Precision: Math.round((row.precision ?? 0) * 100),
    Recall: Math.round((row.recall ?? 0) * 100),
  }));

  return (
    <>
      {!hasRealData && (
        <div className="preview-badge-row">
          <span className="preview-badge">Preview data</span>
          <span className="text-muted" style={{ fontSize: 11 }}>{emptyReason}</span>
        </div>
      )}
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 28 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" horizontal={false} />
          <XAxis type="number" domain={[0, 100]} unit="%" stroke="var(--color-text-secondary)" fontSize={11} />
          <YAxis type="category" dataKey="method" stroke="var(--color-text-secondary)" fontSize={11} width={100} />
          {/* No hover tooltip here -- values are already readable via the bars' own LabelList percentages below. */}
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar dataKey="Accuracy" fill="var(--method-text)" radius={[0, 4, 4, 0]}>
            <LabelList dataKey="Accuracy" position="right" formatter={(v) => `${v}%`} style={{ fontSize: 10, fill: "var(--color-text-secondary)" }} />
          </Bar>
          <Bar dataKey="Precision" fill="var(--method-semantic)" radius={[0, 4, 4, 0]}>
            <LabelList dataKey="Precision" position="right" formatter={(v) => `${v}%`} style={{ fontSize: 10, fill: "var(--color-text-secondary)" }} />
          </Bar>
          <Bar dataKey="Recall" fill="var(--color-accent-rose)" radius={[0, 4, 4, 0]}>
            <LabelList dataKey="Recall" position="right" formatter={(v) => `${v}%`} style={{ fontSize: 10, fill: "var(--color-text-secondary)" }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </>
  );
}

// Recharts' default tooltip box was far too large and covered most of the chart on hover, so this is a compact replacement.
function AnalyticsTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="analytics-tooltip">
      <div className="analytics-tooltip__date">{formatShortDate(label)}</div>
      {payload.map((entry) => (
        <div key={entry.dataKey} className="analytics-tooltip__row">
          <span className="analytics-tooltip__swatch" style={{ background: entry.color }} />
          <span>{entry.name}: {msToSeconds(entry.value).toFixed(2)}s</span>
        </div>
      ))}
    </div>
  );
}

// Average Response Time Over Time -- line chart, operational (never
// reacts to the evaluation backend toggle)
function ResponseTimeChart({ series }) {
  if (!series.length) {
    return <p className="text-muted analytics-empty-state">No analytics data is available for this period.</p>;
  }
  return (
    <ResponsiveContainer width="100%" height={270}>
      <LineChart data={series} margin={{ top: 4, left: 4, right: 12, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
        <XAxis
          dataKey="date"
          stroke="var(--color-text-secondary)"
          fontSize={11}
          tickFormatter={formatShortDate}
          tickMargin={8}
          minTickGap={24}
        />
        <YAxis
          stroke="var(--color-text-secondary)"
          fontSize={11}
          domain={[0, "auto"]}
          tickFormatter={(ms) => `${Math.round(msToSeconds(ms))}s`}
          width={36}
        />
        <Tooltip content={<AnalyticsTooltip />} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Line type="monotone" dataKey="exact_text_ms" name="Exact Text Search" stroke="var(--method-text)" strokeWidth={2} dot={false} connectNulls />
        <Line type="monotone" dataKey="semantic_ms" name="Semantic Search" stroke="var(--method-semantic)" strokeWidth={2} dot={false} connectNulls />
        <Line type="monotone" dataKey="speech_to_text_ms" name="Speech-to-Text" stroke="var(--method-speech)" strokeWidth={2} dot={false} connectNulls />
      </LineChart>
    </ResponsiveContainer>
  );
}

// No hover tooltip: the center total, legend, and per-row percent/count already make every value readable without one.
function DistributionDonut({ distribution, totalQueries }) {
  if (!distribution.length) {
    return <p className="text-muted analytics-empty-state">No analytics data is available for this period.</p>;
  }
  const data = distribution.map((entry) => ({
    name: SEARCH_TYPE_LABEL[entry.search_type],
    value: entry.count,
    percent: entry.percent,
    color: SEARCH_TYPE_COLOR[entry.search_type],
  }));
  return (
    <div className="donut-wrap">
      <ResponsiveContainer width="100%" height={210}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={2}>
            {data.map((entry) => (
              <Cell key={entry.name} fill={entry.color} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      <div className="donut-center">
        <strong>{totalQueries.toLocaleString()}</strong>
        <span>Total Queries</span>
      </div>
      <div className="distribution-list">
        {distribution.map((entry) => (
          <div key={entry.search_type} className="distribution-row">
            <span className="distribution-swatch" style={{ background: SEARCH_TYPE_COLOR[entry.search_type] }} />
            <span style={{ flex: 1 }}>{SEARCH_TYPE_LABEL[entry.search_type]}</span>
            <strong>{entry.percent}%</strong>
            <span className="text-muted">({entry.count.toLocaleString()})</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Must match the backend's CREATABLE_SEARCH_TYPES; run_test_cases doesn't support audio-query test cases yet, so speech_to_text would just produce a 422.
const CREATABLE_SEARCH_TYPES = ["exact_text", "semantic"];
const SEARCH_SCOPE_LABEL = { my_library: "My Library", shared_library: "Shared Library", both: "Both" };

const EMPTY_TEST_CASE_FORM = {
  testName: "",
  queryText: "",
  searchType: "exact_text",
  searchScope: "both",
  expectedVideoId: "",
  expectedStartTime: "",
  expectedEndTime: "",
  toleranceSeconds: "",
};

// Deliberately just a create form, not a management table; this only needs to get a few real rows in so POST /evaluation/run has something to execute against.
function CreateTestCaseForm() {
  const [isOpen, setIsOpen] = useState(false);
  const [videos, setVideos] = useState(null);
  const [isLoadingVideos, setIsLoadingVideos] = useState(false);
  const [videosError, setVideosError] = useState("");
  const [form, setForm] = useState(EMPTY_TEST_CASE_FORM);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  function open() {
    setIsOpen(true);
    setSuccessMessage("");
    if (videos == null && !isLoadingVideos) {
      setIsLoadingVideos(true);
      setVideosError("");
      videoService
        .listVideos()
        .then(setVideos)
        .catch((err) => setVideosError(getErrorMessage(err, "Couldn't load uploads to pick from.")))
        .finally(() => setIsLoadingVideos(false));
    }
  }

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function handleSubmit(event) {
    event.preventDefault();
    setSubmitError("");
    setIsSubmitting(true);
    const payload = {
      test_name: form.testName.trim(),
      query_text: form.queryText.trim(),
      search_type: form.searchType,
      search_scope: form.searchScope,
      expected_video_id: Number(form.expectedVideoId),
      expected_start_time: Number(form.expectedStartTime),
      expected_end_time: Number(form.expectedEndTime),
      ...(form.toleranceSeconds !== "" ? { timestamp_tolerance_seconds: Number(form.toleranceSeconds) } : {}),
    };
    analyticsService
      .createEvaluationTestCase(payload)
      .then((created) => {
        setSuccessMessage(`"${created.test_name}" was created.`);
        setForm(EMPTY_TEST_CASE_FORM);
      })
      .catch((err) => setSubmitError(getErrorMessage(err, "Couldn't create this test case.")))
      .finally(() => setIsSubmitting(false));
  }

  if (!isOpen) {
    return (
      <button type="button" className="btn btn--outline btn--sm" onClick={open}>
        <Icon name="plus" size={14} />
        <span>Add Test Case</span>
      </button>
    );
  }

  return (
    <div className="ui-card analytics-card create-test-case-card">
      <div className="page-header-row" style={{ marginBottom: 8 }}>
        <h3 style={{ fontSize: 14 }}>Add Evaluation Test Case</h3>
        <button type="button" className="menu-trigger" aria-label="Close" onClick={() => setIsOpen(false)}>
          <Icon name="x" size={16} />
        </button>
      </div>
      <p className="text-muted" style={{ fontSize: 12, marginTop: 0 }}>
        A query paired with the video + timestamp window it should retrieve. Used by "Run Evaluation" (Swagger)
        to score real search results.
      </p>

      <form onSubmit={handleSubmit} className="create-test-case-form">
        <div className="form-field">
          <label className="form-label">Test Name</label>
          <input
            type="text" className="text-input" required
            value={form.testName} onChange={(e) => updateField("testName", e.target.value)}
          />
        </div>

        <div className="form-field">
          <label className="form-label">Query Text</label>
          <input
            type="text" className="text-input" required
            value={form.queryText} onChange={(e) => updateField("queryText", e.target.value)}
          />
        </div>

        <div className="create-test-case-form__row">
          <div className="form-field">
            <label className="form-label">Search Type</label>
            <select
              className="select-input" value={form.searchType}
              onChange={(e) => updateField("searchType", e.target.value)}
            >
              {CREATABLE_SEARCH_TYPES.map((t) => (
                <option key={t} value={t}>{SEARCH_TYPE_LABEL[t]}</option>
              ))}
            </select>
          </div>
          <div className="form-field">
            <label className="form-label">Search Scope</label>
            <select
              className="select-input" value={form.searchScope}
              onChange={(e) => updateField("searchScope", e.target.value)}
            >
              {Object.entries(SEARCH_SCOPE_LABEL).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="form-field">
          <label className="form-label">Expected Video</label>
          {isLoadingVideos ? (
            <p className="text-muted" style={{ fontSize: 12.5, margin: 0 }}>Loading uploads...</p>
          ) : videosError ? (
            <p className="form-error" style={{ margin: 0 }}>{videosError}</p>
          ) : (
            <select
              className="select-input" required
              value={form.expectedVideoId}
              onChange={(e) => updateField("expectedVideoId", e.target.value)}
            >
              <option value="" disabled>Select an upload...</option>
              {(videos ?? []).map((v) => (
                <option key={v.id} value={v.id}>
                  {v.title} ({v.media_type === "audio" ? "Audio" : "Video"}, #{v.id})
                </option>
              ))}
            </select>
          )}
        </div>

        <div className="create-test-case-form__row">
          <div className="form-field">
            <label className="form-label">Expected Start (sec)</label>
            <input
              type="number" step="0.1" min="0" className="text-input" required
              value={form.expectedStartTime} onChange={(e) => updateField("expectedStartTime", e.target.value)}
            />
          </div>
          <div className="form-field">
            <label className="form-label">Expected End (sec)</label>
            <input
              type="number" step="0.1" min="0" className="text-input" required
              value={form.expectedEndTime} onChange={(e) => updateField("expectedEndTime", e.target.value)}
            />
          </div>
          <div className="form-field">
            <label className="form-label">Tolerance (sec)</label>
            <input
              type="number" step="0.1" min="0" className="text-input" placeholder="5.0"
              value={form.toleranceSeconds} onChange={(e) => updateField("toleranceSeconds", e.target.value)}
            />
          </div>
        </div>

        {submitError && <p className="form-error">{submitError}</p>}
        {successMessage && <p style={{ color: "var(--color-success)", fontSize: 12.5 }}>{successMessage}</p>}

        <button type="submit" className="btn btn--admin btn--sm" disabled={isSubmitting}>
          {isSubmitting ? "Creating..." : "Create Test Case"}
        </button>
      </form>
    </div>
  );
}

const PIPELINE_ITEMS = [
  { key: "media_processed", label: "Media Processed", icon: "upload", modifier: "pipeline-item--media" },
  { key: "transcript_segments_generated", label: "Transcript Segments Generated", icon: "type-t", modifier: "pipeline-item--segments" },
  { key: "clips_created", label: "Clips Created", icon: "film", modifier: "pipeline-item--clips" },
  { key: "failed_uploads", label: "Failed Uploads", icon: "alert-triangle", modifier: "pipeline-item--failed" },
];

export default function Analytics() {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [draftFrom, setDraftFrom] = useState("");
  const [draftTo, setDraftTo] = useState("");
  const [searchBackend, setSearchBackend] = useState("postgresql");

  const [operational, setOperational] = useState(null);
  const [isLoadingOperational, setIsLoadingOperational] = useState(true);
  const [operationalError, setOperationalError] = useState("");

  const [evaluation, setEvaluation] = useState(null);
  const [isLoadingEvaluation, setIsLoadingEvaluation] = useState(true);
  const [evaluationError, setEvaluationError] = useState("");

  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState("");

  // Operational analytics -- date range only, never the evaluation toggle
  useEffect(() => {
    let cancelled = false;
    setIsLoadingOperational(true);
    setOperationalError("");
    analyticsService
      .getOperationalAnalytics({ dateFrom: dateFrom || undefined, dateTo: dateTo || undefined })
      .then((data) => {
        if (cancelled) return;
        setOperational(data);
        // First load only: adopt the backend's own resolved default range so the date inputs show what was actually queried.
        if (!dateFrom && !dateTo) {
          setDateFrom(data.date_from);
          setDateTo(data.date_to);
          setDraftFrom(data.date_from);
          setDraftTo(data.date_to);
        }
      })
      .catch((err) => {
        if (!cancelled) setOperationalError(getErrorMessage(err, "Couldn't load analytics for this period."));
      })
      .finally(() => {
        if (!cancelled) setIsLoadingOperational(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dateFrom, dateTo]);

  // Evaluation analytics -- date range + evaluation backend toggle
  useEffect(() => {
    if (!dateFrom || !dateTo) return undefined; // wait for the operational effect to resolve the default range first
    let cancelled = false;
    setIsLoadingEvaluation(true);
    setEvaluationError("");
    analyticsService
      .getEvaluationAnalytics({ dateFrom, dateTo, searchBackend })
      .then((data) => {
        if (!cancelled) setEvaluation(data);
      })
      .catch((err) => {
        if (!cancelled) setEvaluationError(getErrorMessage(err, "Couldn't load evaluation results for this period."));
      })
      .finally(() => {
        if (!cancelled) setIsLoadingEvaluation(false);
      });
    return () => {
      cancelled = true;
    };
  }, [dateFrom, dateTo, searchBackend]);

  function handleApplyDateRange() {
    if (!draftFrom || !draftTo) return;
    setDateFrom(draftFrom);
    setDateTo(draftTo);
  }

  function handleExport() {
    setIsExporting(true);
    setExportError("");
    analyticsService
      .fetchAnalyticsCsvBlob({ dateFrom, dateTo, searchBackend })
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `recall_analytics_${dateFrom}_${dateTo}.csv`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      })
      .catch((err) => setExportError(getErrorMessage(err, "Couldn't export this report.")))
      .finally(() => setIsExporting(false));
  }

  const dateRangeLabel = dateFrom && dateTo ? `${dateFrom} to ${dateTo}` : "Loading...";

  const hasRealSummary = evaluation && evaluation.backend_available && evaluation.summary;
  const summaryData = hasRealSummary ? evaluation.summary : PREVIEW_EVALUATION_SUMMARY;
  const summaryEmptyReason = evaluation && (
    !evaluation.backend_available
      ? evaluation.unavailable_reason
      : evaluation.unavailable_reason || "Evaluation has not been run yet."
  );

  return (
    <div>
      <div className="page-header-row">
        <div>
          <h1 className="page-title">
            Analytics &amp; Evaluation
            <img src={greenLeafImg} alt="" className="page-title-leaf" />
          </h1>
          <p className="page-subtitle">System performance and search effectiveness overview.</p>
        </div>
        <div className="analytics-header-controls">
          <div className="analytics-date-controls">
            <Icon name="calendar" size={14} />
            <input type="date" className="analytics-date-input" value={draftFrom} onChange={(e) => setDraftFrom(e.target.value)} aria-label="From date" />
            <span className="text-muted">to</span>
            <input type="date" className="analytics-date-input" value={draftTo} onChange={(e) => setDraftTo(e.target.value)} aria-label="To date" />
            <button type="button" className="btn btn--secondary btn--sm" onClick={handleApplyDateRange}>Apply</button>
          </div>
          <button type="button" className="btn btn--outline btn--sm" onClick={handleExport} disabled={isExporting || !dateFrom}>
            <Icon name="download" size={14} />
            <span>{isExporting ? "Exporting..." : "Export Report"}</span>
          </button>
        </div>
      </div>
      {exportError && <p className="form-error">{exportError}</p>}

      <div className="eval-toggle-row">
        <span className="text-muted" style={{ fontSize: 12.5 }}>Evaluation Backend:</span>
        <div className="eval-toggle">
          <button type="button" className={searchBackend === "postgresql" ? "active" : ""} onClick={() => setSearchBackend("postgresql")}>PostgreSQL</button>
          <button type="button" className={searchBackend === "elasticsearch" ? "active" : ""} onClick={() => setSearchBackend("elasticsearch")}>Elasticsearch</button>
        </div>
        <span className="text-muted" style={{ fontSize: 12.5 }}>{dateRangeLabel}</span>
        <span style={{ marginLeft: "auto" }}>
          <CreateTestCaseForm />
        </span>
      </div>

      {operationalError && <p className="form-error">{operationalError}</p>}

      <div className="stat-grid">
        <StatCard
          icon="target"
          label="Search Accuracy"
          value={evaluation && evaluation.overall_accuracy != null ? `${Math.round(evaluation.overall_accuracy * 100)}%` : "--"}
          deltaLabel={
            isLoadingEvaluation ? "Loading..." : evaluation && evaluation.overall_accuracy == null
              ? (evaluation.unavailable_reason || "Evaluation has not been run yet.")
              : null
          }
          accentColor="var(--method-text)"
          transparent
          infoText={KPI_INFO_TEXT.searchAccuracy}
        />
        <StatCard
          icon="clock"
          label="Average Response Time"
          value={operational ? formatMs(operational.average_response_time_ms.value) : "--"}
          deltaLabel={operational ? deltaLabelFor(operational.average_response_time_ms) : (isLoadingOperational ? "Loading..." : null)}
          deltaDirection="down"
          accentColor="var(--method-semantic)"
          transparent
          infoText={KPI_INFO_TEXT.averageResponseTime}
        />
        <StatCard
          icon="file-text"
          label="Media Files Indexed"
          value={operational ? operational.media_files_indexed.value : "--"}
          deltaLabel={operational ? deltaLabelFor(operational.media_files_indexed) : (isLoadingOperational ? "Loading..." : null)}
          accentColor="var(--method-text)"
          transparent
          infoText={KPI_INFO_TEXT.mediaFilesIndexed}
        />
        <StatCard
          icon="bar-chart"
          label="Queries Processed"
          value={operational ? operational.queries_processed.value.toLocaleString() : "--"}
          deltaLabel={operational ? deltaLabelFor(operational.queries_processed) : (isLoadingOperational ? "Loading..." : null)}
          accentColor="var(--method-semantic)"
          transparent
          infoText={KPI_INFO_TEXT.queriesProcessed}
        />
      </div>

      <div className="analytics-grid analytics-panel-grid--thirds">
        <div className="ui-card analytics-card analytics-chart-card">
          <h3 style={{ fontSize: 14 }}>Search Method Performance Comparison</h3>
          {isLoadingEvaluation ? <p className="text-muted analytics-empty-state">Loading...</p> : evaluation && <MethodComparisonChart evaluation={evaluation} />}
        </div>

        <div className="ui-card analytics-card analytics-chart-card">
          <h3 style={{ fontSize: 14 }}>Average Response Time Over Time</h3>
          {isLoadingOperational ? <p className="text-muted analytics-empty-state">Loading...</p> : operational && <ResponseTimeChart series={operational.response_time_series} />}
        </div>

        <div className="ui-card analytics-card analytics-chart-card">
          <h3 style={{ fontSize: 14 }}>Query Distribution by Search Type</h3>
          {isLoadingOperational ? (
            <p className="text-muted analytics-empty-state">Loading...</p>
          ) : operational && (
            <>
              <DistributionDonut distribution={operational.query_distribution} totalQueries={operational.total_queries} />
              {operational.usage_insight && <p className="text-muted" style={{ marginTop: 12 }}>{operational.usage_insight}</p>}
            </>
          )}
        </div>
      </div>

      <div className="analytics-grid analytics-panel-grid--row3">
        <div className="ui-card analytics-card analytics-card--compact">
          <h3 style={{ fontSize: 14 }}>Retrieval Quality by Search Method</h3>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Search Method</th>
                  <th>Precision</th>
                  <th>Recall</th>
                  <th>F1 Score</th>
                </tr>
              </thead>
              <tbody>
                {["exact_text", "semantic", "speech_to_text"].map((type) => {
                  const row = evaluation?.method_rows.find((r) => r.search_type === type);
                  const fmt = (v) => (v == null ? "--" : v.toFixed(2));
                  return (
                    <tr key={type}>
                      <td>{SEARCH_TYPE_LABEL[type]}</td>
                      <td>{row ? fmt(row.precision) : "--"}</td>
                      <td>{row ? fmt(row.recall) : "--"}</td>
                      <td>{row ? fmt(row.f1) : "--"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-muted" style={{ marginTop: 8, marginBottom: 0 }}>
            {evaluation && !evaluation.backend_available
              ? evaluation.unavailable_reason
              : evaluation && !evaluation.method_rows.length
                ? (evaluation.unavailable_reason || "Evaluation has not been run yet.")
                : "Higher values indicate better performance."}
          </p>
        </div>

        <div className="ui-card analytics-card">
          <h3 style={{ fontSize: 14 }}>Search Pipeline Health</h3>
          <div className="pipeline-grid">
            {PIPELINE_ITEMS.map((item) => (
              <div key={item.key} className={`pipeline-item ${item.modifier}`}>
                <span className="pipeline-item__icon">
                  <Icon name={item.icon} size={18} />
                </span>
                <div className="pipeline-item__text">
                  <p className="pipeline-item__label">{item.label}</p>
                  <p className="pipeline-item__value">{operational ? operational.pipeline_health[item.key] : "--"}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="ui-card analytics-card">
          <h3 style={{ fontSize: 14 }}>Evaluation Summary</h3>
          {!hasRealSummary && (
            <div className="preview-badge-row">
              <span className="preview-badge">Preview data</span>
              <span className="text-muted" style={{ fontSize: 11 }}>{summaryEmptyReason}</span>
            </div>
          )}
          {evaluation ? (
            TROPHIES.map((trophy) => (
              <div key={trophy.label} className="trophy-card">
                <span className={`trophy-icon ${trophy.iconClass}`}>
                  <Icon name={trophy.icon} size={16} />
                </span>
                <div>
                  <p className="trophy-label">{trophy.label}</p>
                  <p className="trophy-value">{SEARCH_TYPE_LABEL[summaryData[trophy.key]] ?? "--"}</p>
                  <p className="trophy-note">{summaryData[trophy.noteKey]}</p>
                </div>
              </div>
            ))
          ) : (
            <p className="text-muted analytics-empty-state">Loading...</p>
          )}
        </div>
      </div>

      {evaluationError && <p className="form-error">{evaluationError}</p>}

      <div className="ui-card analytics-card" style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <span className="text-muted"><Icon name="info" size={14} /> Search methods shown: Exact Text, Semantic, Speech-to-Text (Audio Fingerprinting is not a live search method).</span>
        <span className="text-muted">{evaluation && evaluation.last_run_at ? `Last evaluation run: ${new Date(evaluation.last_run_at).toLocaleString()}` : "No evaluation run recorded yet."}</span>
      </div>
    </div>
  );
}
