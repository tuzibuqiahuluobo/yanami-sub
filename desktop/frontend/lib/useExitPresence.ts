"use client";

import { useEffect, useState } from "react";

export function motionIsReduced(): boolean {
  return document.documentElement.dataset.motion === "off" ||
    (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
}

/** Keep a closing surface briefly for its exit animation, never for input. */
export function useExitPresence(open: boolean) {
  const [present, setPresent] = useState(open);
  useEffect(() => {
    if (open) {
      setPresent(true);
      return;
    }
    if (!present) return;
    if (motionIsReduced()) {
      setPresent(false);
      return;
    }
    const timer = window.setTimeout(() => setPresent(false), 220);
    return () => window.clearTimeout(timer);
  }, [open, present]);
  return {
    present: open || present,
    finish: () => { if (!open) setPresent(false); },
  };
}
