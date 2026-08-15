import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import "../styles/pages/LibraryCategories.css";

import Icon from "../components/Icon";
import * as categoryService from "../services/categoryService";
import greenLeafImg from "../assets/decorations/greenLeaf-trimmed.png";
import flowerBranchImg from "../assets/decorations/flowerBranch-trimmed.png";
import branchImg from "../assets/decorations/branch-trimmed.png";

// Collection name -> URL slug
function slugify(name) {
  return name.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

// All collections grid, reached via Library's "View all collections"
export default function LibraryCategories({ basePath = "/library" }) {
  const [categories, setCategories] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const [openMenuId, setOpenMenuId] = useState(null);
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState("");

  useEffect(() => {
    categoryService
      .listCategories()
      .then(setCategories)
      .catch(() => setError("Couldn't load your collections. Please try again."))
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    if (openMenuId === null) return undefined;
    function handleClickOutside(event) {
      if (!event.target.closest(".menu-wrap")) {
        setOpenMenuId(null);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [openMenuId]);

  function startRename(category) {
    setRenameValue(category.name);
    setRenamingId(category.id);
    setOpenMenuId(null);
  }

  function cancelRename() {
    setRenamingId(null);
    setRenameValue("");
  }

  function confirmRename(categoryId) {
    const name = renameValue.trim();
    if (!name) return;
    categoryService
      .renameCategory(categoryId, name)
      .then((updated) => {
        setCategories((prev) => prev.map((c) => (c.id === categoryId ? updated : c)));
        setRenamingId(null);
      })
      .catch(() => {
        // Leave input open so the user can see it didn't save and retry.
      });
  }

  return (
    <div>
      <Link to={basePath} className="back-to-library">
        <Icon name="arrow-left" size={14} />
        Back to Library
      </Link>

      <div className="page-header-row">
        <div>
          <h1 className="page-title">
            Collections
            <img src={greenLeafImg} alt="" className="page-title-leaf" />
          </h1>
          <p className="page-subtitle">All of your collections, in one place.</p>
        </div>
      </div>

      {isLoading ? (
        <p className="text-muted">Loading your collections...</p>
      ) : error ? (
        <p style={{ color: "var(--color-danger)" }}>{error}</p>
      ) : categories.length === 0 ? (
        <p className="text-muted">You haven&apos;t created any collections yet.</p>
      ) : (
        <div className="category-grid">
          {categories.map((c) => (
            <div key={c.id} className="category-card">
              {renamingId === c.id ? (
                <div className="collection-create-row" style={{ flex: "1 1 auto", minWidth: 0 }}>
                  <input
                    type="text"
                    className="text-input"
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") confirmRename(c.id);
                      if (e.key === "Escape") cancelRename();
                    }}
                    autoFocus
                  />
                  <button
                    type="button"
                    className="collection-create-confirm"
                    aria-label="Save name"
                    disabled={!renameValue.trim()}
                    onClick={() => confirmRename(c.id)}
                  >
                    <Icon name="check" size={14} />
                  </button>
                </div>
              ) : (
                <Link to={`${basePath}/categories/${slugify(c.name)}`} className="category-card__link">
                  <span className="category-card__icon">
                    <Icon name="folder" size={18} />
                  </span>
                  <div>
                    <p className="category-card__name">{c.name}</p>
                    <p className="category-card__count">{c.video_count} items</p>
                  </div>
                </Link>
              )}
              <div className="menu-wrap">
                <button
                  type="button"
                  className="menu-trigger"
                  aria-label="Collection options"
                  onClick={() => setOpenMenuId((current) => (current === c.id ? null : c.id))}
                >
                  <Icon name="more-vertical" size={16} />
                </button>
                {openMenuId === c.id && (
                  <div className="menu-dropdown">
                    <button type="button" onClick={() => startRename(c)}>Rename Collection</button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="page-corner-decorations">
        <img src={branchImg} alt="" className="page-corner-decorations__img page-corner-decorations__img--left" />
        <img src={flowerBranchImg} alt="" className="page-corner-decorations__img page-corner-decorations__img--right" />
      </div>
    </div>
  );
}
