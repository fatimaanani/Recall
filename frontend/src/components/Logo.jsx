import "./Logo.css";
import logoMarkImg from "../assets/icons/ReCallLogo-icon.svg";

// Brand mark, cropped icon + styled wordmark
export default function Logo({ size = "md" }) {
  const dimension = size === "sm" ? 28 : 40;
  return (
    <div className={`logo logo--${size}`}>
      <img
        src={logoMarkImg}
        alt="ReCall"
        width={dimension}
        height={dimension}
        className="logo__mark"
      />
      <span className="logo__wordmark">
        Re<span className="logo__wordmark-accent">Call</span>
      </span>
    </div>
  );
}
