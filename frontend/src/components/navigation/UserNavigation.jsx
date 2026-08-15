import { NavLink, useLocation } from "react-router-dom";

import Icon from "../Icon";
import "./Navigation.css";

// User sidebar items
const USER_NAV_ITEMS = [
  { label: "Home", to: "/home", icon: "home" },
  { label: "Scene Viewer", to: "/scene-viewer", icon: "film" },
  { label: "Upload", to: "/uploads", icon: "cloud-upload" },
  { label: "Library", to: "/library", icon: "folder" },
  { label: "Settings", to: "/settings", icon: "settings" },
];

// Scene Viewer has no standalone destination (real route is /scene-viewer/:resultId, see App.jsx), so the sidebar item only links to the current URL when already on a valid result route, otherwise it renders disabled.
const SCENE_VIEWER_RESULT_PATH = /^\/scene-viewer\/[1-9]\d*$/;

export default function UserNavigation() {
  const location = useLocation();
  const onValidSceneViewerRoute = SCENE_VIEWER_RESULT_PATH.test(location.pathname);

  return (
    <ul className="nav-list">
      {USER_NAV_ITEMS.map((item) => {
        if (item.to === "/scene-viewer" && !onValidSceneViewerRoute) {
          return (
            <li key={item.to}>
              <span
                className="nav-item nav-item--disabled"
                aria-disabled="true"
                title="Select a search result first."
              >
                <Icon name={item.icon} size={18} />
                {item.label}
              </span>
            </li>
          );
        }
        const to = item.to === "/scene-viewer" ? location.pathname : item.to;
        return (
          <li key={item.to}>
            <NavLink to={to} className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
              <Icon name={item.icon} size={18} />
              {item.label}
            </NavLink>
          </li>
        );
      })}
    </ul>
  );
}
