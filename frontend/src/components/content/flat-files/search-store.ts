import { create } from "zustand";

// The /files search query lives here because the input is the topbar's search
// bar while the results render in the page below — one search, two components.
interface FilesSearchState {
  query: string;
  setQuery: (query: string) => void;
}

export const useFilesSearch = create<FilesSearchState>((set) => ({
  query: "",
  setQuery: (query) => set({ query }),
}));
