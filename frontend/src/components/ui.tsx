import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Link } from "react-router-dom";

import { meterClass } from "../format";
import { Icon, type IconName } from "./Icon";

/* --------------------------------------------------------------- toasts */

type ToastKind = "success" | "error" | "info";

interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastApi {
  push: (kind: ToastKind, message: string) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const push = useCallback((kind: ToastKind, message: string) => {
    const id = nextId.current++;
    setItems((current) => [...current, { id, kind, message }]);
    setTimeout(() => setItems((current) => current.filter((item) => item.id !== id)), 4600);
  }, []);

  const api = useMemo<ToastApi>(
    () => ({
      push,
      success: (message) => push("success", message),
      error: (message) => push("error", message),
      info: (message) => push("info", message),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {items.map((item) => (
          <div key={item.id} className={`toast toast-${item.kind}`}>
            <Icon
              name={item.kind === "success" ? "check" : item.kind === "error" ? "alert" : "info"}
              size={15}
            />
            <span>{item.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast must be used inside ToastProvider");
  return api;
}

/* ------------------------------------------------------------- primitives */

export function Spinner({ onAccent = false }: { onAccent?: boolean }) {
  return <span className={`spinner${onAccent ? " on-accent" : ""}`} aria-hidden="true" />;
}

export function LoadingLine({ text = "Loading…" }: { text?: string }) {
  return (
    <div className="loading-line" role="status">
      <Spinner />
      <span>{text}</span>
    </div>
  );
}

export function ErrorState({
  title = "Couldn't load this view",
  message,
  onRetry,
  retryLabel = "Try again",
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon name="alert" size={20} />
      </div>
      <div className="empty-title">{title}</div>
      <div className="empty-desc">{message}</div>
      <div className="empty-desc faint">Nothing was changed — this screen only reads data.</div>
      {onRetry && (
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          <Icon name="refresh" size={14} />
          {retryLabel}
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  icon = "candidates",
  title,
  description,
  action,
}: {
  icon?: IconName;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon name={icon} size={20} />
      </div>
      <div className="empty-title">{title}</div>
      {description && <div className="empty-desc">{description}</div>}
      {action}
    </div>
  );
}

export function Notice({
  kind = "neutral",
  icon = "info",
  children,
}: {
  kind?: "neutral" | "accent" | "warn" | "danger";
  icon?: IconName;
  children: ReactNode;
}) {
  const cls = kind === "neutral" ? "notice" : `notice notice-${kind}`;
  return (
    <div className={cls}>
      <Icon name={icon} size={15} />
      <div>{children}</div>
    </div>
  );
}

export function Stat({
  label,
  value,
  tone,
  sub,
  to,
}: {
  label: string;
  value: number | string;
  tone?: "accent" | "success" | "warn";
  sub?: string;
  to?: string;
}) {
  const body = (
    <>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {sub && <div className="stat-label faint">{sub}</div>}
    </>
  );
  if (to) {
    return (
      <Link className={`stat stat-link${tone ? ` ${tone}` : ""}`} to={to}>
        {body}
      </Link>
    );
  }
  return <div className={`stat${tone ? ` ${tone}` : ""}`}>{body}</div>;
}

export function Meter({ value, suffix = "%" }: { value: number; suffix?: string }) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className="meter" title={`${clamped}${suffix}`}>
      <div className="meter-track">
        <div className={meterClass(clamped)} style={{ width: `${clamped}%` }} />
      </div>
      <span className="meter-value">
        {Math.round(clamped)}
        {suffix}
      </span>
    </div>
  );
}

export function Progress({ percent, meta }: { percent: number; meta?: ReactNode }) {
  const clamped = Math.max(0, Math.min(100, percent));
  return (
    <div>
      <div
        className="progress"
        role="progressbar"
        aria-valuenow={Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="progress-fill" style={{ width: `${clamped}%` }} />
      </div>
      {meta && <div className="progress-meta">{meta}</div>}
    </div>
  );
}

export function Card({
  id,
  title,
  kicker,
  actions,
  children,
  bodyClass,
  className,
}: {
  id?: string;
  title?: ReactNode;
  kicker?: string;
  actions?: ReactNode;
  children: ReactNode;
  bodyClass?: string;
  className?: string;
}) {
  const heading = typeof title === "string" ? <h2 className="card-title">{title}</h2> : title;
  return (
    <section id={id} className={`card${className ? ` ${className}` : ""}`}>
      {(title || actions) && (
        <header className="card-header">
          {kicker ? (
            <div className="card-heading">
              <span className={`kicker${kicker === "Human decision" ? " kicker-human" : ""}`}>
                {kicker}
              </span>
              {heading}
            </div>
          ) : (
            heading
          )}
          {actions && <div className="card-header-actions">{actions}</div>}
        </header>
      )}
      <div className={bodyClass ?? "card-body"}>{children}</div>
    </section>
  );
}

export function Modal({
  title,
  onClose,
  children,
  footer,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    ref.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      if (previous && previous.isConnected) previous.focus();
    };
  }, [onClose]);

  return (
    <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}>
        <header className="modal-header">
          <h2>{title}</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close dialog">
            <Icon name="close" size={16} />
          </button>
        </header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-footer">{footer}</footer>}
      </div>
    </div>
  );
}

export function Pagination({
  page,
  pageSize,
  total,
  onPage,
  onPageSize,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
  onPageSize: (size: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(total, page * pageSize);
  return (
    <div className="pagination">
      <span>
        {first}–{last} of {total}
      </span>
      <label className="row small" style={{ gap: 6 }}>
        <span className="faint">Rows</span>
        <select
          className="select"
          style={{ width: 72, height: 28, padding: "0 26px 0 8px", fontSize: 12.5 }}
          value={pageSize}
          onChange={(event) => onPageSize(Number(event.target.value))}
          aria-label="Rows per page"
        >
          {[25, 50, 100].map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
        aria-label="Previous page"
      >
        <Icon name="chevron-left" size={14} />
      </button>
      <span className="num">
        {page} / {pages}
      </span>
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        disabled={page >= pages}
        onClick={() => onPage(page + 1)}
        aria-label="Next page"
      >
        <Icon name="chevron-right" size={14} />
      </button>
    </div>
  );
}
