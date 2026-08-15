import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import "../styles/pages/Splash.css";

import { useAuth } from "../context/AuthContext";
import { markSplashPlayed } from "../utils/splashGate";
import splashImg from "../assets/icons/SplashLandscape.png";

// Minimum time splash stays on screen
const MIN_DISPLAY_MS = 2000;

// Must match splash-fade-out animation duration in Splash.css
const SPLASH_EXIT_MS = 400;

// App entry point, mounted at "/"
export default function Splash() {
  const navigate = useNavigate();
  const { isAuthenticated, isAdmin, isLoading } = useAuth();
  const [minTimeElapsed, setMinTimeElapsed] = useState(false);
  const [isExiting, setIsExiting] = useState(false);
  // Guards against double-triggering exit, ref not state (see effect below)
  const hasStartedExit = useRef(false);

  useEffect(() => {
    // Mark as soon as Splash mounts, so a refresh detour doesn't loop back
    markSplashPlayed();
    const timer = setTimeout(() => setMinTimeElapsed(true), MIN_DISPLAY_MS);
    return () => clearTimeout(timer);
  }, []);

  // isExiting deliberately not a dependency, would self-trigger a re-run and
  // cancel navigate() via cleanup before it fires; hasStartedExit avoids that
  useEffect(() => {
    if (!minTimeElapsed || isLoading || hasStartedExit.current) return;
    hasStartedExit.current = true;
    setIsExiting(true);
    const timer = setTimeout(() => {
      if (isAuthenticated) {
        navigate(isAdmin ? "/admin/users" : "/home", { replace: true });
      } else {
        navigate("/role-selection", { replace: true });
      }
    }, SPLASH_EXIT_MS);
    return () => clearTimeout(timer);
  }, [minTimeElapsed, isLoading, isAuthenticated, isAdmin, navigate]);

  return (
    <div className={`splash-page${isExiting ? " splash-page--exiting" : ""}`}>
      <img src={splashImg} alt="ReCall" className="splash-image" />
    </div>
  );
}
