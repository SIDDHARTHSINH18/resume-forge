/** App-wide "the data changed" signal so pages can refetch after a mutation. */

export const DATA_CHANGED_EVENT = "meritos:data-changed";

export function emitDataChanged(): void {
  window.dispatchEvent(new Event(DATA_CHANGED_EVENT));
}

export function onDataChanged(handler: () => void): () => void {
  window.addEventListener(DATA_CHANGED_EVENT, handler);
  return () => window.removeEventListener(DATA_CHANGED_EVENT, handler);
}
