"use client";

import { CircleHelp } from "lucide-react";
import { useId, useLayoutEffect, useRef, useState } from "react";
import { useLanguage } from "./LanguageProvider";

export function FieldHelp({ label, hint }: { label: string; hint: string }) {
  const { language } = useLanguage();
  const id = useId();
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLSpanElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const tipRef = useRef<HTMLSpanElement>(null);

  useLayoutEffect(() => {
    if (!open) return;
    const anchor = anchorRef.current!;
    const trigger = triggerRef.current!;
    const tip = tipRef.current!;
    const close = () => setOpen(false);
    const position = () => {
      const rect = trigger.getBoundingClientRect();
      if (rect.bottom <= 0 || rect.top >= window.innerHeight) {
        close();
        return;
      }
      const edge = 8;
      const below = window.innerHeight - rect.bottom;
      const above = rect.top;
      const top = below < tip.offsetHeight + edge && above > below
        ? rect.top - tip.offsetHeight + 1 : rect.bottom - 1;
      const left = rect.left + rect.width / 2 - tip.offsetWidth / 2;
      tip.style.top = `${Math.max(edge, top)}px`;
      tip.style.left = `${Math.max(edge, Math.min(left, window.innerWidth - tip.offsetWidth - edge))}px`;
    };
    tip.showPopover?.();
    position();
    const outside = (event: PointerEvent) => {
      if (!anchor.contains(event.target as Node)) close();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    window.addEventListener("resize", position);
    window.addEventListener("scroll", position, true);
    return () => {
      tip.hidePopover?.();
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
      window.removeEventListener("resize", position);
      window.removeEventListener("scroll", position, true);
    };
  }, [open]);

  return <span className="field-with-help">
    <span>{label}</span>
    <span ref={anchorRef} className="field-help-anchor"
      onPointerEnter={(event) => { if (event.pointerType === "mouse") setOpen(true); }}
      onPointerLeave={(event) => {
        if (event.pointerType === "mouse" && !triggerRef.current?.matches(":focus-visible")) setOpen(false);
      }}>
      <button ref={triggerRef} type="button" className="field-help-trigger"
        aria-label={language === "en" ? `Help: ${label}` : `${label}说明`}
        aria-describedby={id}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(event) => {
          if (open && event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            setOpen(false);
          }
        }}
        onClick={() => setOpen(true)}>
        <CircleHelp size={15} aria-hidden="true" />
      </button>
      <span ref={tipRef} id={id} popover="manual" hidden={!open} role="tooltip" className="field-help-tooltip">
        {hint}
      </span>
    </span>
  </span>;
}
