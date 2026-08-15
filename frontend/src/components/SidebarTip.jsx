import "./SidebarTip.css";
import AssetPlaceholder from "./AssetPlaceholder";

// Sidebar tip card, mascot + line (or a pre-composed image, with optional dark variant)
export default function SidebarTip({ text, mascotPath, image, darkImage }) {
  if (image) {
    if (darkImage) {
      return (
        <div className="sidebar-tip sidebar-tip--image">
          <img src={image} alt={text || ""} className="sidebar-tip__swap-light" />
          <img src={darkImage} alt={text || ""} className="sidebar-tip__swap-dark" />
        </div>
      );
    }
    return (
      <div className="sidebar-tip sidebar-tip--image">
        <img src={image} alt={text || ""} className="sidebar-tip__full-image" />
      </div>
    );
  }

  return (
    <div className="sidebar-tip">
      <p className="sidebar-tip__text">{text}</p>
      <AssetPlaceholder path={mascotPath} width={72} height={72} shape="circle" className="sidebar-tip__mascot" />
    </div>
  );
}
