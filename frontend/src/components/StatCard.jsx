import { useEffect, useRef, useState } from "react";

import Icon from "./Icon";
import "./StatCard.css";

// Stat tile used by Analytics. accentColor tints the icon chip and value text; transparent applies Analytics' tinted-card background; infoText shows a toggleable info popover.
export default function StatCard({ icon, label, value, deltaLabel, deltaDirection = "up", accentColor, transparent = false, infoText }) {
  const [isInfoOpen, setIsInfoOpen] = useState(false);
  const wrapperRef = useRef(null);

  useEffect(() => {
    if (!isInfoOpen) return undefined;
    function handleClickOutside(event) {
      if (wrapperRef.current && !wrapperRef.current.contains(event.target)) {
        setIsInfoOpen(false);
      }
    }
    function handleKeyDown(event) {
      if (event.key === "Escape") setIsInfoOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isInfoOpen]);

  return (
    <div className={`stat-card${transparent ? " stat-card--transparent" : ""}`}>
      {infoText && (
        <div className="stat-card__info-wrap" ref={wrapperRef}>
          <button
            type="button"
            className="stat-card__info-btn"
            aria-label={`About ${label}`}
            aria-haspopup="dialog"
            aria-expanded={isInfoOpen}
            onClick={() => setIsInfoOpen((open) => !open)}
          >
            <Icon name="info" size={13} />
          </button>
          {isInfoOpen && (
            <div className="stat-card__popover" role="dialog" aria-label={`About ${label}`}>
              {infoText}
            </div>
          )}
        </div>
      )}
      <div className="stat-card__header">
        <span className="stat-card__icon" style={accentColor ? { color: accentColor, background: "color-mix(in srgb, " + accentColor + " 18%, var(--color-surface))" } : undefined}>
          <Icon name={icon} size={18} />
        </span>
        <span className="stat-card__label">{label}</span>
      </div>
      <div className="stat-card__value" style={accentColor ? { color: accentColor } : undefined}>{value}</div>
      {deltaLabel && (
        <div className={`stat-card__delta stat-card__delta--${deltaDirection}`}>
          <Icon name={deltaDirection === "up" ? "arrow-right" : "arrow-right"} size={12} className="stat-card__delta-icon" />
          {deltaLabel}
        </div>
      )}
    </div>
  );
}
