import { flushSync } from "react-dom";


type ViewTransitionDocument = Document & {
  startViewTransition?: (update: () => void) => unknown;
};


/** Run a small shared-element transition when both app and OS allow motion. */
export function runInterfaceTransition(update: () => void): void {
  const startViewTransition = (document as ViewTransitionDocument).startViewTransition;
  const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

  if (
    document.documentElement.dataset.motion === "off" ||
    reduceMotion ||
    !startViewTransition
  ) {
    update();
    return;
  }

  startViewTransition.call(document, () => flushSync(update));
}
