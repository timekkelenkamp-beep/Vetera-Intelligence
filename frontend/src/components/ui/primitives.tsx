import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { motion } from "motion/react";
import { cn } from "@/lib/utils";
import type { Tone } from "@/lib/labels";

/* ------------------------------------------------------------------ Button */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap font-medium transition-all duration-150 select-none disabled:opacity-45 disabled:pointer-events-none active:scale-[0.98]",
  {
    variants: {
      variant: {
        primary: "bg-accent text-white hover:bg-accent-ink shadow-[0_1px_2px_rgba(0,0,0,0.12)]",
        secondary: "bg-surface text-ink hover:bg-surface-sunken",
        outline: "border border-line-strong bg-white text-ink hover:bg-surface",
        ghost: "text-ink-soft hover:bg-surface hover:text-ink",
        danger: "bg-negative-soft text-negative hover:bg-[#f6dcda]",
        link: "text-accent hover:underline underline-offset-2 px-0 h-auto",
      },
      size: { sm: "h-7 px-2.5 text-[12.5px] rounded-lg", md: "h-9 px-3.5 text-[13.5px] rounded-[10px]", lg: "h-11 px-5 text-[15px] rounded-xl", icon: "h-8 w-8 rounded-lg" },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  loading?: boolean;
  icon?: React.ReactNode;
}
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, loading, icon, children, disabled, ...props }, ref) => (
  <button ref={ref} className={cn(buttonVariants({ variant, size }), className)} disabled={disabled || loading} {...props}>
    {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : icon}
    {children}
  </button>
));
Button.displayName = "Button";

/* ------------------------------------------------------------------ Card */
export function Card({ className, interactive, ...props }: React.HTMLAttributes<HTMLDivElement> & { interactive?: boolean }) {
  return (
    <div
      className={cn(
        "rounded-2xl bg-white border border-line shadow-soft",
        interactive && "transition-all duration-200 hover:shadow-lift hover:-translate-y-[1px] cursor-pointer",
        className,
      )}
      {...props}
    />
  );
}
export function CardHeader({ title, subtitle, actions, className }: { title: React.ReactNode; subtitle?: React.ReactNode; actions?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-start justify-between gap-4 px-5 pt-4 pb-3", className)}>
      <div className="min-w-0">
        <h3 className="text-[15px] font-semibold text-ink">{title}</h3>
        {subtitle && <p className="text-[12.5px] text-ink-muted mt-0.5">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ Badge */
const toneClasses: Record<Tone, string> = {
  positive: "bg-positive-soft text-positive",
  negative: "bg-negative-soft text-negative",
  caution: "bg-caution-soft text-caution",
  info: "bg-info-soft text-info",
  neutral: "bg-surface text-ink-muted",
  attention: "bg-[#f3efff] text-[#5b3fb5]",
  accent: "bg-accent-soft text-accent",
};
export function Badge({ tone = "neutral", className, dot, children }: { tone?: Tone; className?: string; dot?: boolean; children: React.ReactNode }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-[2px] text-[11.5px] font-medium whitespace-nowrap", toneClasses[tone], className)}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" />}
      {children}
    </span>
  );
}

/* ------------------------------------------------------------------ Inputs */
const fieldBase =
  "w-full rounded-[10px] border border-line-strong bg-white px-3 text-[13.5px] text-ink placeholder:text-ink-faint transition-shadow focus:outline-none focus:border-accent focus:shadow-ring disabled:bg-surface";
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...p }, ref) => (
  <input ref={ref} className={cn(fieldBase, "h-9", className)} {...p} />
));
Input.displayName = "Input";
export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(({ className, ...p }, ref) => (
  <textarea ref={ref} className={cn(fieldBase, "py-2 min-h-[80px] leading-relaxed", className)} {...p} />
));
Textarea.displayName = "Textarea";
const CHEVRON = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236e6e73' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")";
export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(({ className, children, style, ...p }, ref) => (
  <select
    ref={ref}
    className={cn(fieldBase, "h-9 pr-8 appearance-none", className)}
    style={{ backgroundImage: CHEVRON, backgroundSize: "12px", backgroundPosition: "right 10px center", backgroundRepeat: "no-repeat", ...style }}
    {...p}
  >
    {children}
  </select>
));
Select.displayName = "Select";

export function Field({ label, hint, children, className, required }: { label: string; hint?: React.ReactNode; children: React.ReactNode; className?: string; required?: boolean }) {
  return (
    <label className={cn("block", className)}>
      <span className="block text-[12.5px] font-medium text-ink-soft mb-1">
        {label}
        {required && <span className="text-negative"> *</span>}
      </span>
      {children}
      {hint && <span className="block text-[11.5px] text-ink-muted mt-1">{hint}</span>}
    </label>
  );
}

export function Switch({ checked, onCheckedChange, label, description, disabled }: { checked: boolean; onCheckedChange: (v: boolean) => void; label?: string; description?: string; disabled?: boolean }) {
  return (
    <label className={cn("flex items-start justify-between gap-6 py-1", disabled && "opacity-50")}>
      {label && (
        <span>
          <span className="block text-[13.5px] text-ink">{label}</span>
          {description && <span className="block text-[12px] text-ink-muted mt-0.5 max-w-xl">{description}</span>}
        </span>
      )}
      <SwitchPrimitive.Root
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        className="relative h-[22px] w-[38px] shrink-0 rounded-full bg-[#e3e3e8] transition-colors data-[state=checked]:bg-accent"
      >
        <SwitchPrimitive.Thumb className="block h-[18px] w-[18px] translate-x-[2px] rounded-full bg-white shadow-[0_1px_3px_rgba(0,0,0,0.25)] transition-transform data-[state=checked]:translate-x-[18px]" />
      </SwitchPrimitive.Root>
    </label>
  );
}

/* ------------------------------------------------------------------ Segmented control */
export function Segmented<T extends string>({ value, onChange, options, className }: { value: T; onChange: (v: T) => void; options: { value: T; label: React.ReactNode }[]; className?: string }) {
  return (
    <div className={cn("inline-flex rounded-[10px] bg-surface p-[3px]", className)}>
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={cn("relative h-7 px-3 text-[12.5px] font-medium rounded-[8px] transition-colors", value === o.value ? "text-ink" : "text-ink-muted hover:text-ink")}
        >
          {value === o.value && <motion.span layoutId={`seg-${options.map((x) => x.value).join("")}`} className="absolute inset-0 rounded-[8px] bg-white shadow-[0_1px_3px_rgba(0,0,0,0.1)]" transition={{ type: "spring", bounce: 0.15, duration: 0.35 }} />}
          <span className="relative flex items-center gap-1.5">{o.label}</span>
        </button>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ Feedback */
export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("h-4 w-4 animate-spin text-ink-muted", className)} />;
}

export function Loading({ label = "Laden…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-[13px] text-ink-muted">
      <Spinner /> {label}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-lg bg-surface", className)} />;
}

export function EmptyState({ icon, title, description, action, className }: { icon?: React.ReactNode; title: string; description?: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center text-center py-14 px-6", className)}>
      {icon && <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-surface text-ink-muted [&_svg]:h-5 [&_svg]:w-5">{icon}</div>}
      <h3 className="text-[15px] font-semibold text-ink">{title}</h3>
      {description && <p className="mt-1.5 max-w-md text-[13px] text-ink-muted leading-relaxed">{description}</p>}
      {action && <div className="mt-5 flex gap-2">{action}</div>}
    </div>
  );
}

export function Notice({ tone = "info", title, children, icon, className }: { tone?: Tone; title?: React.ReactNode; children?: React.ReactNode; icon?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex gap-3 rounded-xl px-4 py-3 text-[13px]", toneClasses[tone], className)}>
      {icon && <div className="mt-0.5 shrink-0 [&_svg]:h-4 [&_svg]:w-4">{icon}</div>}
      <div className="min-w-0">
        {title && <div className="font-semibold">{title}</div>}
        {children && <div className={cn("leading-relaxed", title && "mt-0.5", "opacity-90")}>{children}</div>}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ Page layout */
export function PageHeader({ title, subtitle, actions, eyebrow }: { title: React.ReactNode; subtitle?: React.ReactNode; actions?: React.ReactNode; eyebrow?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 mb-7">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1.5 text-[12.5px] font-medium text-ink-muted">{eyebrow}</div>}
        <h1 className="text-[28px] font-semibold tracking-tightest text-ink leading-tight">{title}</h1>
        {subtitle && <p className="mt-1.5 text-[14px] text-ink-muted max-w-3xl">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, hint, icon, onClick }: { label: string; value: React.ReactNode; hint?: React.ReactNode; icon?: React.ReactNode; onClick?: () => void }) {
  return (
    <Card interactive={!!onClick} onClick={onClick} className="p-5">
      <div className="flex items-center justify-between">
        <span className="text-[12.5px] font-medium text-ink-muted">{label}</span>
        {icon && <span className="text-ink-faint [&_svg]:h-4 [&_svg]:w-4">{icon}</span>}
      </div>
      <div className="mt-2 text-[30px] font-semibold tracking-tightest tabular text-ink leading-none">{value}</div>
      {hint && <div className="mt-2 text-[12px] text-ink-muted">{hint}</div>}
    </Card>
  );
}

export function Divider({ className }: { className?: string }) {
  return <div className={cn("h-px bg-line", className)} />;
}

/* ------------------------------------------------------------------ Tooltip */
export function Tip({ content, children, side = "top" }: { content: React.ReactNode; children: React.ReactNode; side?: "top" | "bottom" | "left" | "right" }) {
  return (
    <TooltipPrimitive.Root delayDuration={250}>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content side={side} sideOffset={6} className="z-[100] max-w-xs rounded-lg bg-ink/95 px-2.5 py-1.5 text-[12px] leading-snug text-white shadow-lift backdrop-blur">
          {content}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

export const TooltipProvider = TooltipPrimitive.Provider;

export function KeyValue({ items, className }: { items: { label: string; value: React.ReactNode }[]; className?: string }) {
  return (
    <dl className={cn("grid grid-cols-[minmax(120px,auto)_1fr] gap-x-6 gap-y-2.5 text-[13px]", className)}>
      {items.map((i) => (
        <React.Fragment key={i.label}>
          <dt className="text-ink-muted">{i.label}</dt>
          <dd className="text-ink min-w-0 break-words">{i.value ?? "–"}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}
