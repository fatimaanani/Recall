import "./AudioFilePill.css";

import Icon from "./Icon";

export default function AudioFilePill({ file, onRemove }) {
  if (!file) return null;

  return (
    <div className="audio-file-pill">
      <Icon name="music" size={14} className="audio-file-pill__icon" />
      <span className="audio-file-pill__name" title={file.name}>{file.name}</span>
      <button
        type="button"
        className="audio-file-pill__remove"
        aria-label="Remove selected audio file"
        onClick={onRemove}
      >
        <Icon name="x" size={12} />
      </button>
    </div>
  );
}
