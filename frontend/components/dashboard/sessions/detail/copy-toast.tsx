"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Check } from "lucide-react";

export function CopyToast({ visible }: { visible: boolean }) {
  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 12 }}
          transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
          className="fixed bottom-6 right-6 z-[90] flex items-center gap-2 rounded-full border border-accent/30 bg-[#0D0D0D]/95 backdrop-blur-xl px-3.5 py-2 shadow-[0_20px_60px_-20px_rgba(0,0,0,0.8)]"
          data-testid="copy-toast"
          role="status"
          aria-live="polite"
        >
          <span className="flex h-4 w-4 items-center justify-center rounded-full bg-accent/15 text-accent">
            <Check size={10} strokeWidth={3} />
          </span>
          <span className="text-[12.5px] text-white">Copied!</span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
