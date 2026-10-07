"use client";

import { createContext, useContext, type ReactNode } from "react";
import type { ProductCheckpoint } from "@/lib/types";

const ProductCheckpointContext = createContext<ProductCheckpoint>("latest");

export function ProductCheckpointProvider({ checkpoint, children }: {
  checkpoint?: ProductCheckpoint;
  children: ReactNode;
}) {
  return <ProductCheckpointContext.Provider value={checkpoint ?? "latest"}>{children}</ProductCheckpointContext.Provider>;
}

export function useProductCheckpoint() {
  return useContext(ProductCheckpointContext);
}
