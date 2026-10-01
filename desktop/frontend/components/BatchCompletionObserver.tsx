"use client";
import { useEffect, useRef } from "react";
import { desktopApi } from "@/lib/bridge";
import { playNotification } from "@/lib/notificationSound";
import type { BatchSnapshot } from "@/lib/types";
import { useLanguage } from "./LanguageProvider";
import { useToast } from "./ToastProvider";

/** One global observer, even when the queue page is unmounted. */
export function BatchCompletionObserver({ enabled }: { enabled: boolean }) {
  const { language } = useLanguage();
  const { showSuccess, showNotice } = useToast();
  const previous = useRef<BatchSnapshot | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let stopped = false, inFlight = false;
    const poll = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const current = await desktopApi.getBatchSnapshot();
        if (stopped) return;
        if (previous.current?.state === "running" && current?.batch_id === previous.current.batch_id && current.state !== "running") {
          const done = current.items.filter((item) => item.state === "done" && !item.correction_skipped).length;
          const failed = current.items.filter((item) => item.state === "failed").length;
          const skipped = current.items.length - done - failed;
          const message = language === "en" ? `Batch ended: ${done} complete, ${failed} failed, ${skipped} partial/skipped. Log: ${current.log_path}` : `批处理结束：完成 ${done}，失败 ${failed}，部分完成/跳过 ${skipped}。日志：${current.log_path}`;
          (failed || skipped ? showNotice : showSuccess)(message, `batch-ended-${current.batch_id}-${current.updated_at}`);
          if (current.state === "completed" && failed === 0 && skipped === 0) void playNotification("batch");
        }
        previous.current = current;
      } catch { /* Keep observed state through bridge failures. */ }
      finally { inFlight = false; }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [enabled, language, showSuccess, showNotice]);
  return null;
}
