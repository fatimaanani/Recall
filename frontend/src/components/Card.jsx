// Generic surface card
export default function Card({ className = "", children, ...rest }) {
  return (
    <section className={`ui-card ${className}`} {...rest}>
      {children}
    </section>
  );
}
