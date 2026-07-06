"use client";

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useEscapeKey } from "../hooks/useEscapeKey";

export interface ConfirmOptions {
  title: string;
  /** Extra detail under the title, e.g. "This cannot be undone." */
  body?: string;
  /** Label for the confirm button. Defaults to "Confirm". */
  confirmLabel?: string;
  /** Red confirm button. Defaults to true since most confirms guard deletes. */
  destructive?: boolean;
}

type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn | null>(null);

export function ConfirmDialogProvider({ children }: { children: ReactNode }) {
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const resolveRef = useRef<((value: boolean) => void) | null>(null);

  const confirm = useCallback<ConfirmFn>((opts) => {
    return new Promise<boolean>((resolve) => {
      resolveRef.current = resolve;
      setOptions(opts);
    });
  }, []);

  const settle = useCallback((value: boolean) => {
    resolveRef.current?.(value);
    resolveRef.current = null;
    setOptions(null);
  }, []);

  useEscapeKey(options !== null, () => settle(false));

  const destructive = options?.destructive ?? true;

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {options && (
        <div
          className="fixed inset-0 z-[60] flex cursor-pointer items-center justify-center bg-black/30 px-4"
          onClick={() => settle(false)}
        >
          <div
            role="alertdialog"
            aria-modal="true"
            aria-label={options.title}
            className="w-full max-w-sm rounded-xl border border-border bg-base p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="text-[14px] font-medium text-foreground">
              {options.title}
            </div>
            {options.body && (
              <div className="mt-1.5 text-[12.5px] text-muted-foreground">{options.body}</div>
            )}
            <div className="mt-4 flex justify-end gap-1.5">
              <button
                type="button"
                onClick={() => settle(false)}
                className="cursor-pointer rounded-md border border-border bg-base px-3 py-1.5 text-[12.5px] text-foreground hover:bg-raised"
              >
                Cancel
              </button>
              <button
                type="button"
                autoFocus
                onClick={() => settle(true)}
                className={
                  "cursor-pointer rounded-md px-3 py-1.5 text-[12.5px] font-medium text-white " +
                  (destructive
                    ? "bg-red-600 hover:bg-red-700"
                    : "bg-[var(--color-brand-600)] hover:bg-[var(--color-brand-700)]")
                }
              >
                {options.confirmLabel ?? "Confirm"}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm(): ConfirmFn {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error("useConfirm must be used inside <ConfirmDialogProvider>");
  return ctx;
}
