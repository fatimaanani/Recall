import "./Badge.css";
import { SEARCH_METHOD_META } from "../mocks/mockData";

const STATUS_CLASSES = {
  ready: "badge--status-ready",
  active: "badge--status-ready",
  processing: "badge--status-processing",
  failed: "badge--status-failed",
  suspended: "badge--status-failed",
};

export function MethodBadge({ method, className = "" }) {
  const meta = SEARCH_METHOD_META[method];
  if (!meta) return null;
  return <span className={`badge ${meta.className} ${className}`}>{meta.label}</span>;
}

export function StatusBadge({ status, label, className = "" }) {
  const statusClass = STATUS_CLASSES[status] ?? "badge--status-neutral";
  return <span className={`badge ${statusClass} ${className}`}>{label ?? status}</span>;
}
