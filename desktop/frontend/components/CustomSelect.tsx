"use client";

import { ChevronDown } from "lucide-react";
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { useLanguage } from "./LanguageProvider";
import { useExitPresence } from "@/lib/useExitPresence";


export interface SelectOption {
  value: string;
  label: string;
}

/**
 * Never wrap this in a `<label>`. The menu renders inside the component, so a
 * surrounding label makes every option a non-interactive descendant of it, and
 * the browser answers a click there by forwarding a second click to the label's
 * control -- this trigger. Selecting an option then closed the menu and the
 * forwarded click reopened it, which read as "the dropdown will not close".
 * Use a plain element plus `ariaLabel` for the caption instead.
 */

interface CustomSelectProps {
  value: string;
  options: SelectOption[];
  disabled?: boolean;
  ariaLabel?: string;
  onChange: (value: string) => void;
}


export function CustomSelect({
  value,
  options,
  disabled,
  ariaLabel,
  onChange,
}: CustomSelectProps) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const presence = useExitPresence(open);
  const [activeIndex, setActiveIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLUListElement>(null);
  const [menuLayout, setMenuLayout] = useState({ above: false, maxHeight: 420, left: 0, width: 0, edge: 0 });
  const listboxId = useId();
  const triggerId = `${listboxId}-trigger`;

  const selectedOption = options.find((option) => option.value === value);
  const selectedIndex = Math.max(
    0,
    options.findIndex((option) => option.value === value),
  );

  const openMenu = useCallback(
    (index = selectedIndex) => {
      if (disabled || options.length === 0) {
        return;
      }
      setActiveIndex(Math.max(0, Math.min(index, options.length - 1)));
      setOpen(true);
    },
    [disabled, options.length, selectedIndex],
  );

  const selectIndex = useCallback(
    (index: number) => {
      const option = options[index];
      if (!option) {
        return;
      }
      onChange(option.value);
      setActiveIndex(index);
      setOpen(false);
    },
    [onChange, options],
  );

  const handleTriggerKeyDown = (
    event: ReactKeyboardEvent<HTMLButtonElement>,
  ) => {
    if (disabled || options.length === 0) {
      return;
    }
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        if (!open) {
          openMenu(selectedIndex);
        } else {
          setActiveIndex((index) => Math.min(index + 1, options.length - 1));
        }
        break;
      case "ArrowUp":
        event.preventDefault();
        if (!open) {
          openMenu(selectedIndex);
        } else {
          setActiveIndex((index) => Math.max(index - 1, 0));
        }
        break;
      case "Home":
        event.preventDefault();
        openMenu(0);
        break;
      case "End":
        event.preventDefault();
        openMenu(options.length - 1);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        if (open) {
          selectIndex(activeIndex);
        } else {
          openMenu();
        }
        break;
      case "Escape":
        if (open) {
          event.preventDefault();
          setOpen(false);
        }
        break;
      case "Tab":
        setOpen(false);
        break;
    }
  };

  const handleOutsideClick = useCallback((event: MouseEvent) => {
    if (
      containerRef.current &&
      !containerRef.current.contains(event.target as Node)
    ) {
      setOpen(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      document.addEventListener("mousedown", handleOutsideClick);
      return () =>
        document.removeEventListener("mousedown", handleOutsideClick);
    }
  }, [open, handleOutsideClick]);

  useLayoutEffect(() => {
    if (!open) return;
    const position = () => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      if (rect.bottom < 0 || rect.top > window.innerHeight) { setOpen(false); return; }
      const below = window.innerHeight - rect.bottom - 12;
      const above = rect.top - 12;
      const useAbove = below < 240 && above > below;
      const width = Math.min(rect.width, window.innerWidth - 16);
      setMenuLayout({ above: useAbove, maxHeight: Math.max(0, Math.min(420, useAbove ? above : below)),
        width, left: Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)),
        edge: useAbove ? window.innerHeight - rect.top + 6 : rect.bottom + 6 });
    };
    position();
    // The browser top layer escapes glass-panel stacking and clipping, even in dialogs.
    menuRef.current?.showPopover?.();
    window.addEventListener("resize", position);
    window.addEventListener("scroll", position, true);
    return () => { window.removeEventListener("resize", position); window.removeEventListener("scroll", position, true); };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const menu = menuRef.current;
    const item = menu?.children[activeIndex] as HTMLElement | undefined;
    if (!menu || !item) return;
    if (item.offsetTop < menu.scrollTop) menu.scrollTop = item.offsetTop;
    else if (item.offsetTop + item.offsetHeight > menu.scrollTop + menu.clientHeight) {
      menu.scrollTop = item.offsetTop + item.offsetHeight - menu.clientHeight;
    }
  }, [open, activeIndex, menuLayout.maxHeight]);

  return (
    <div
      ref={containerRef}
      className={`custom-select${open ? " is-open" : ""}${disabled ? " is-disabled" : ""}`}
    >
      <button
        id={triggerId}
        type="button"
        role="combobox"
        className="custom-select-trigger"
        disabled={disabled}
        aria-label={
          ariaLabel
            ? `${ariaLabel}：${selectedOption?.label ?? t.common.select}`
            : undefined
        }
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-activedescendant={
          open ? `${listboxId}-option-${activeIndex}` : undefined
        }
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          if (open) {
            setOpen(false);
          } else {
            openMenu();
          }
        }}
        onKeyDown={handleTriggerKeyDown}
      >
        <span className="custom-select-value">
          {selectedOption?.label ?? t.common.select}
        </span>
        <ChevronDown size={15} className="custom-select-arrow" aria-hidden="true" />
      </button>

      {presence.present ? (
        <ul
          ref={menuRef}
          id={listboxId}
          className="custom-select-menu"
          popover="manual"
          data-side={menuLayout.above ? "top" : "bottom"}
          style={{ maxHeight: menuLayout.maxHeight, left: menuLayout.left, width: menuLayout.width,
            top: menuLayout.above ? "auto" : menuLayout.edge,
            bottom: menuLayout.above ? menuLayout.edge : "auto" }}
          data-closing={!open || undefined}
          inert={!open}
          aria-hidden={!open || undefined}
          onAnimationEnd={(event) => { if (event.target === event.currentTarget) presence.finish(); }}
          role="listbox"
          aria-labelledby={triggerId}
        >
          {options.map((option, index) => (
            <li
              id={`${listboxId}-option-${index}`}
              key={option.value}
              role="option"
              aria-selected={option.value === value}
              className={`custom-select-option${option.value === value ? " is-selected" : ""}${index === activeIndex ? " is-active" : ""}`}
              onMouseEnter={() => setActiveIndex(index)}
              onMouseDown={(event) => event.preventDefault()}
              onClick={(event) => { event.preventDefault(); event.stopPropagation(); selectIndex(index); }}
            >
              {option.label}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
