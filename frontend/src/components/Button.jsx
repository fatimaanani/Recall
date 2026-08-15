import { Link } from "react-router-dom";
import Icon from "./Icon";

// Button, renders <Link> when "to" given, otherwise <button>
export default function Button({
  variant = "primary",
  icon,
  iconPosition = "left",
  to,
  type = "button",
  className = "",
  children,
  ...rest
}) {
  const classes = `btn btn--${variant} ${className}`.trim();
  const content = (
    <>
      {icon && iconPosition === "left" && <Icon name={icon} size={17} />}
      <span>{children}</span>
      {icon && iconPosition === "right" && <Icon name={icon} size={17} />}
    </>
  );

  if (to) {
    return (
      <Link to={to} className={classes} {...rest}>
        {content}
      </Link>
    );
  }

  return (
    <button type={type} className={classes} {...rest}>
      {content}
    </button>
  );
}
