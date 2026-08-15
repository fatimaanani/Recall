import "./Pagination.css";

import Icon from "./Icon";

export default function Pagination({ currentPage, totalPages, onPageChange }) {
  // Always renders the bar, even for a single page, rather than hiding when totalPages <= 1.
  return (
    <div className="pagination">
      <button
        type="button"
        className="pagination__btn"
        aria-label="Previous page"
        onClick={() => onPageChange(Math.max(1, currentPage - 1))}
        disabled={currentPage === 1}
      >
        <Icon name="chevron-left" size={16} />
      </button>
      {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
        <button
          key={page}
          type="button"
          className={`pagination__page${page === currentPage ? " active" : ""}`}
          onClick={() => onPageChange(page)}
        >
          {page}
        </button>
      ))}
      <button
        type="button"
        className="pagination__btn"
        aria-label="Next page"
        onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
        disabled={currentPage === totalPages}
      >
        <Icon name="chevron-right" size={16} />
      </button>
    </div>
  );
}
