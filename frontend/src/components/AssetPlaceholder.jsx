import Icon from "./Icon";
import "./AssetPlaceholder.css";

// Stand-in for missing artwork (mascots, illustrations, avatars)
export default function AssetPlaceholder({
  path,
  shape = "rect",
  width = 120,
  height = 120,
  label,
  className = "",
}) {
  return (
    <div
      className={`asset-placeholder asset-placeholder--${shape} ${className}`}
      style={{ width, height }}
      title={path}
    >
      <Icon name="image" size={Math.min(width, height) * 0.3} />
      <span className="asset-placeholder__path">{path}</span>
      {label && <span className="asset-placeholder__label">{label}</span>}
    </div>
  );
}
