import { Outlet, useLocation } from "react-router-dom";
import "./AppShell.css";

import Logo from "../components/Logo";
import UserNavigation from "../components/navigation/UserNavigation";
import SidebarTip from "../components/SidebarTip";
import TopBar from "../components/TopBar";
import Icon from "../components/Icon";
import { useDarkMode } from "../hooks/useDarkMode";
import homeTipImg from "../assets/mascots/homePageMascot-final.png";
import homeTipDarkImg from "../assets/mascots/homePageMascotDarkMode-final.png";
import libraryTipImg from "../assets/mascots/libraryNavMascot-final.png";
import libraryTipDarkImg from "../assets/mascots/libraryNavMascotDarkMode-final.png";
import uploadsTipImg from "../assets/mascots/uploadNavMascot-final.png";
import uploadsTipDarkImg from "../assets/mascots/uploadNavMascotDarkMode-final.png";
import resultsTipImg from "../assets/mascots/resultsMascot.png";
import resultsTipDarkImg from "../assets/mascots/resultsMascotDarkMode.png";
import sceneViewerTipImg from "../assets/mascots/sceneViewerMascot.png";
import sceneViewerTipDarkImg from "../assets/mascots/sceneViewerMascotDarkMode.png";
import settingsTipImg from "../assets/mascots/settingsNavPic-final.png";
import settingsTipDarkImg from "../assets/mascots/settingsNavPicDarkMode-final.png";

// Per-route sidebar tip, mascot + line. Matched against location.pathname below.
const TIPS_BY_PATH = {
  "/home": { text: "I'm here to help you find that scene!", image: homeTipImg, darkImage: homeTipDarkImg },
  "/home/results": { text: "Found something interesting? Click a result to view the scene!", image: resultsTipImg, darkImage: resultsTipDarkImg },
  "/scene-viewer": { text: "Here's the moment we found!", image: sceneViewerTipImg, darkImage: sceneViewerTipDarkImg },
  "/library": { text: "All your stories, safely archived.", image: libraryTipImg, darkImage: libraryTipDarkImg },
  "/uploads": { text: "Let's add some new stories to the archive!", image: uploadsTipImg, darkImage: uploadsTipDarkImg },
  "/settings": { text: "Good systems are built with care.", image: settingsTipImg, darkImage: settingsTipDarkImg },
};
const DEFAULT_TIP = { text: "Every moment matters.", mascotPath: "assets/mascots/search-cat.png" };

// Exact match first, otherwise the first key that pathname sits under (e.g. "/scene-viewer/42" under "/scene-viewer").
function resolveTip(pathname) {
  if (TIPS_BY_PATH[pathname]) return TIPS_BY_PATH[pathname];
  const parentKey = Object.keys(TIPS_BY_PATH).find((key) => pathname.startsWith(`${key}/`));
  return parentKey ? TIPS_BY_PATH[parentKey] : DEFAULT_TIP;
}

export default function UserLayout() {
  const location = useLocation();
  const [darkMode, setDarkMode] = useDarkMode();
  const tip = resolveTip(location.pathname);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar__brand-wrap">
          <Logo size="sm" />
        </div>

        <UserNavigation />

        <div className="sidebar-spacer" />

        <SidebarTip text={tip.text} mascotPath={tip.mascotPath} image={tip.image} darkImage={tip.darkImage} />

        <div className="dark-mode-row">
          <span>
            <Icon name="moon" size={15} /> Dark Mode
          </span>
          <button
            type="button"
            className={`toggle-switch${darkMode ? " on" : ""}`}
            aria-pressed={darkMode}
            onClick={() => setDarkMode((v) => !v)}
          />
        </div>
      </aside>

      <main className="app-content">
        <TopBar />
        <Outlet />
      </main>
    </div>
  );
}
