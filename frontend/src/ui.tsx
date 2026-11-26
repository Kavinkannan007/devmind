import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva } from "class-variance-authority";
import { Link } from "react-router-dom";
import { CircleAlert, Layers3, LoaderCircle } from "lucide-react";
const button = cva("button", {
  variants: {
    variant: { primary: "primary", secondary: "secondary", quiet: "quiet" },
  },
  defaultVariants: { variant: "primary" },
});
export function Button({
  asChild,
  variant,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  asChild?: boolean;
  variant?: "primary" | "secondary" | "quiet";
}) {
  const Component = asChild ? Slot : "button";
  return <Component className={button({ variant, className })} {...props} />;
}
export function Brand() {
  return (
    <Link className="brand" to="/" aria-label="DevMind home">
      <span className="brand-mark">
        <Layers3 size={22} />
      </span>
      DevMind
    </Link>
  );
}
export function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="notice" role="alert">
      <CircleAlert size={16} />
      <span>{children}</span>
    </div>
  );
}
export function Loading({ label = "Loading workspace" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={18} />
      {label}…
    </div>
  );
}
export function Footer() {
  return (
    <footer>
      <Brand />
      <span>Intelligence for every codebase.</span>
      <a href="#top">Back to top</a>
    </footer>
  );
}
