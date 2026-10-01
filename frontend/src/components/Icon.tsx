export type IconName =
  | "funnel"
  | "dashboard"
  | "profiles"
  | "candidates"
  | "processing"
  | "reviews"
  | "exports"
  | "settings"
  | "upload"
  | "search"
  | "close"
  | "check"
  | "x"
  | "alert"
  | "info"
  | "chevron-left"
  | "chevron-right"
  | "chevron-down"
  | "sort"
  | "sort-asc"
  | "sort-desc"
  | "refresh"
  | "sparkle"
  | "file"
  | "download"
  | "external"
  | "mail"
  | "phone"
  | "pin"
  | "link"
  | "clock"
  | "user"
  | "note"
  | "clipboard"
  | "shield"
  | "eye";

const paths: Record<IconName, string> = {
  funnel: "M3 5h18l-7 8v5l-4 2v-7L3 5z",
  dashboard: "M4 4h6v7H4zM14 4h6v4h-6zM14 11h6v9h-6zM4 14h6v6H4z",
  profiles: "M4 5h16M4 12h16M4 19h10M4 4v16",
  candidates:
    "M8 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM2.5 20c0-3 2.5-5 5.5-5s5.5 2 5.5 5M16 4h5M16 8h5M16 12h5M18.5 16v4M16.5 18h4",
  processing: "M3 12h4l2.5-6 4 12 2.5-6h5",
  reviews: "M9 3H5a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V9l-6-6H9zM14 3v6h6M8.5 14.5l2 2 4-4.5",
  exports: "M12 3v12M7.5 10.5 12 15l4.5-4.5M4 19h16M4 19v-4M20 19v-4",
  settings: "M4 7h10M18 7h2M4 17h2M10 17h10M4 12h4M12 12h8M14 5v4M8 15v4M8 10v4",
  upload: "M12 16V4M7.5 8.5 12 4l4.5 4.5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3",
  search: "M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13zM15.5 15.5 20 20",
  close: "M6 6l12 12M18 6 6 18",
  check: "M4.5 12.5 10 18 19.5 7",
  x: "M6.5 6.5l11 11M17.5 6.5l-11 11",
  alert: "M12 3 2.5 20h19L12 3zM12 9.5V14M12 17.2v.3",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v5M12 7.5v.5",
  "chevron-left": "m14.5 6-6 6 6 6",
  "chevron-right": "m9.5 6 6 6-6 6",
  "chevron-down": "m6 9.5 6 6 6-6",
  sort: "M8 9.5 12 5l4 4.5M8 14.5l4 4.5 4-4.5",
  "sort-asc": "M12 19V5M6.5 10.5 12 5l5.5 5.5",
  "sort-desc": "M12 5v14M6.5 13.5 12 19l5.5-5.5",
  refresh: "M20 12a8 8 0 1 1-2.5-5.8M20 4v4.5h-4.5",
  sparkle: "M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8L19 16z",
  file: "M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7l-4-4zM14 3v4h4M9 13h6M9 17h6",
  download: "M12 4v11M7.5 11 12 15.5 16.5 11M5 19h14",
  external: "M14 4h6v6M20 4l-9 9M10 5H6a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-4",
  mail: "M4 6h16v12H4zM4 7l8 6 8-6",
  phone: "M6 3h3l1.5 4.5L8.5 9a12 12 0 0 0 6.5 6.5l1.5-2L21 15v3a2 2 0 0 1-2 2A16 16 0 0 1 4 5a2 2 0 0 1 2-2z",
  pin: "M12 21s7-6 7-11a7 7 0 1 0-14 0c0 5 7 11 7 11zM12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z",
  link: "M10 14a4 4 0 0 0 6 .5l2.5-2.5a4 4 0 1 0-5.7-5.7L11.5 7.5M14 10a4 4 0 0 0-6-.5L5.5 12a4 4 0 1 0 5.7 5.7l1.3-1.2",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3.5 2",
  user: "M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4.5 21c0-3.5 3-6 7.5-6s7.5 2.5 7.5 6",
  note: "M5 4h14v12l-4 4H5zM15 20v-4h4M9 9h6M9 13h4",
  clipboard: "M9 4h6v2.5H9zM7 5H6a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-1M9 12l2 2 4-4",
  shield: "M12 3 5 6v5c0 5 3 8.4 7 10 4-1.6 7-5 7-10V6l-7-3zM9 12l2 2 4-4",
  eye: "M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
};

interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
  strokeWidth?: number;
}

export function Icon({ name, size = 16, className, strokeWidth = 1.8 }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <path d={paths[name]} />
    </svg>
  );
}
