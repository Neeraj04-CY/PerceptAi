import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        ref={ref}
        className={cn(
          "flex h-10 w-full rounded-lg border border-white/[0.08] bg-white/[0.02] px-3.5 py-2 text-sm text-white placeholder:text-white/30",
          "focus:outline-none focus:border-accent/40 focus:bg-white/[0.03] focus:ring-1 focus:ring-accent/20",
          "transition-all duration-200 font-sans",
          className
        )}
        {...props}
      />
    );
  }
);
Input.displayName = "Input";

export { Input };
