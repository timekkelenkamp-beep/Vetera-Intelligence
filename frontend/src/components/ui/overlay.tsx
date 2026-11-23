import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as Dropdown from "@radix-ui/react-dropdown-menu";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export function Dialog({ open, onOpenChange, title, description, children, footer, size = "md" }: {
  open: boolean; onOpenChange: (v: boolean) => void; title: React.ReactNode; description?: React.ReactNode;
  children?: React.ReactNode; footer?: React.ReactNode; size?: "sm" | "md" | "lg" | "xl" | "full";
}) {
  const w = { sm: "max-w-md", md: "max-w-xl", lg: "max-w-3xl", xl: "max-w-5xl", full: "max-w-[min(1400px,96vw)]" }[size];
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/20 backdrop-blur-[2px] data-[state=open]:animate-[fadeIn_150ms_ease-out]" />
        <DialogPrimitive.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 w-[calc(100vw-32px)] -translate-x-1/2 -translate-y-1/2 rounded-2xl bg-white shadow-[0_24px_80px_rgba(0,0,0,0.18)] border border-line",
            "max-h-[92vh] flex flex-col data-[state=open]:animate-[popIn_180ms_cubic-bezier(0.2,0.9,0.3,1.1)]",
            w,
          )}
        >
          <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-3">
            <div className="min-w-0">
              <DialogPrimitive.Title className="text-[17px] font-semibold text-ink">{title}</DialogPrimitive.Title>
              {description ? (
                <DialogPrimitive.Description className="mt-1 text-[13px] text-ink-muted">{description}</DialogPrimitive.Description>
              ) : (
                <DialogPrimitive.Description className="sr-only">{typeof title === "string" ? title : "Dialoog"}</DialogPrimitive.Description>
              )}
            </div>
            <DialogPrimitive.Close className="rounded-full p-1.5 text-ink-muted hover:bg-surface hover:text-ink" aria-label="Sluiten">
              <X className="h-4 w-4" />
            </DialogPrimitive.Close>
          </div>
          <div className="px-6 pb-5 overflow-y-auto">{children}</div>
          {footer && <div className="flex justify-end gap-2 border-t border-line px-6 py-3.5 bg-surface/50 rounded-b-2xl">{footer}</div>}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

export function Tabs({ value, onValueChange, tabs, children, className }: {
  value: string; onValueChange: (v: string) => void; tabs: { value: string; label: React.ReactNode; count?: number }[];
  children: React.ReactNode; className?: string;
}) {
  return (
    <TabsPrimitive.Root value={value} onValueChange={onValueChange} className={className}>
      <TabsPrimitive.List className="mb-6 flex gap-1 border-b border-line overflow-x-auto">
        {tabs.map((t) => (
          <TabsPrimitive.Trigger
            key={t.value}
            value={t.value}
            className="relative -mb-px whitespace-nowrap border-b-2 border-transparent px-3 pb-2.5 pt-1 text-[13.5px] font-medium text-ink-muted transition-colors hover:text-ink data-[state=active]:border-ink data-[state=active]:text-ink"
          >
            {t.label}
            {t.count !== undefined && t.count > 0 && <span className="ml-1.5 rounded-full bg-surface px-1.5 py-px text-[11px] text-ink-muted tabular">{t.count}</span>}
          </TabsPrimitive.Trigger>
        ))}
      </TabsPrimitive.List>
      {children}
    </TabsPrimitive.Root>
  );
}
export const TabPanel = ({ value, children }: { value: string; children: React.ReactNode }) => (
  <TabsPrimitive.Content value={value} className="focus:outline-none">{children}</TabsPrimitive.Content>
);

export function Menu({ trigger, items }: { trigger: React.ReactNode; items: ({ label: string; icon?: React.ReactNode; onSelect: () => void; danger?: boolean } | "sep")[] }) {
  return (
    <Dropdown.Root>
      <Dropdown.Trigger asChild>{trigger}</Dropdown.Trigger>
      <Dropdown.Portal>
        <Dropdown.Content align="end" sideOffset={6} className="z-50 min-w-[200px] rounded-xl border border-line bg-white/95 p-1 shadow-lift backdrop-blur">
          {items.map((it, i) =>
            it === "sep" ? (
              <Dropdown.Separator key={i} className="my-1 h-px bg-line" />
            ) : (
              <Dropdown.Item
                key={i}
                onSelect={it.onSelect}
                className={cn("flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-1.5 text-[13px] outline-none data-[highlighted]:bg-surface [&_svg]:h-3.5 [&_svg]:w-3.5", it.danger ? "text-negative" : "text-ink")}
              >
                {it.icon}
                {it.label}
              </Dropdown.Item>
            ),
          )}
        </Dropdown.Content>
      </Dropdown.Portal>
    </Dropdown.Root>
  );
}

/** Zijpaneel (sheet) voor detailweergaven zoals de bronviewer. */
export function Sheet({ open, onOpenChange, title, subtitle, children, width = "min(980px, 94vw)" }: {
  open: boolean; onOpenChange: (v: boolean) => void; title: React.ReactNode; subtitle?: React.ReactNode; children: React.ReactNode; width?: string;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/15 data-[state=open]:animate-[fadeIn_150ms_ease-out]" />
        <DialogPrimitive.Content style={{ width }} className="fixed right-0 top-0 z-50 h-full bg-white shadow-[0_0_60px_rgba(0,0,0,0.18)] flex flex-col data-[state=open]:animate-[slideIn_220ms_cubic-bezier(0.2,0.9,0.3,1)]">
          <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
            <div className="min-w-0">
              <DialogPrimitive.Title className="text-[16px] font-semibold text-ink truncate">{title}</DialogPrimitive.Title>
              <DialogPrimitive.Description className={subtitle ? "mt-0.5 text-[12.5px] text-ink-muted" : "sr-only"}>{subtitle || "Detail"}</DialogPrimitive.Description>
            </div>
            <DialogPrimitive.Close className="rounded-full p-1.5 text-ink-muted hover:bg-surface hover:text-ink" aria-label="Sluiten">
              <X className="h-4 w-4" />
            </DialogPrimitive.Close>
          </div>
          <div className="flex-1 min-h-0 overflow-hidden">{children}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
