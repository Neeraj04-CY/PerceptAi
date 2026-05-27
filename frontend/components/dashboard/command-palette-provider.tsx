"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { usePathname } from "next/navigation";
import { CommandPalette } from "./command-palette";

interface PaletteCtx {
  open: () => void;
  close: () => void;
  isOpen: boolean;
}

const CommandPaletteContext = createContext<PaletteCtx | null>(null);

export function CommandPaletteProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  const onOpen = useCallback(() => setOpen(true), []);
  const onClose = useCallback(() => setOpen(false), []);

  // Global Cmd/Ctrl+K listener
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === "Escape") {
        setOpen((v) => (v ? false : v));
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Auto-close on route change so the palette doesn't linger
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  return (
    <CommandPaletteContext.Provider value={{ open: onOpen, close: onClose, isOpen: open }}>
      {children}
      <CommandPalette open={open} onClose={onClose} />
    </CommandPaletteContext.Provider>
  );
}

export function useCommandPalette(): PaletteCtx {
  const ctx = useContext(CommandPaletteContext);
  if (!ctx) {
    // Safe noop fallback so consumers don't crash outside the provider
    return { open: () => {}, close: () => {}, isOpen: false };
  }
  return ctx;
}
