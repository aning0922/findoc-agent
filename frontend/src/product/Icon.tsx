export type IconName =
  | "library"
  | "research"
  | "history"
  | "upload"
  | "search"
  | "chevron"
  | "arrow"
  | "file"
  | "check"
  | "clock"
  | "alert"
  | "close"
  | "panel"
  | "quote"
  | "plus"
  | "refresh"
  | "external"
  | "shield"
  | "send"
  | "copy"
  | "info"
  | "filter"
  | "trend"
  | "book"
  | "link"
  | "menu";
const paths: Record<IconName, string> = {
  library: "M4 4h6v16H4z M14 4h6v16h-6z M7 8h0 M17 8h0 M4 16h6 M14 16h6",
  research:
    "M9 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-4 M10 14l2-5 6-6 3 3-6 6-5 2Z M16 5l3 3",
  history: "M3 11a9 9 0 1 1 2.6 7 M3 4v7h7 M12 7v5l3 2",
  upload: "M12 16V3 M7 8l5-5 5 5 M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4",
  search: "M21 21l-5-5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z",
  chevron: "M9 5l7 7-7 7",
  arrow: "M4 12h16 M14 6l6 6-6 6",
  file: "M14 2H5a1 1 0 0 0-1 1v18a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V7l-5-5Z M14 2v6h6 M8 12h8 M8 16h6",
  check: "M5 12l4 4L19 6",
  clock: "M12 8v4l3 2 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  alert: "M12 3 2 21h20L12 3Z M12 9v5 M12 17h.01",
  close: "M6 6l12 12 M18 6 6 18",
  panel:
    "M4 3h16a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z M14 3v18 M17 9l2 3-2 3",
  quote: "M3 5h7v7H6c0 4-3 6-3 6 M14 5h7v7h-4c0 4-3 6-3 6",
  plus: "M12 5v14 M5 12h14",
  refresh:
    "M20 7a9 9 0 0 0-15-1L2 10 M2 4v6h6 M4 17a9 9 0 0 0 15 1l3-4 M22 20v-6h-6",
  external:
    "M14 3h7v7 M21 3 10 14 M10 3H4a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1v-6",
  shield: "M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6l-9-4Z M8 12l3 3 5-6",
  send: "M22 2 9 15 M22 2l-7 20-6-7-7-6 20-7Z",
  copy: "M9 9h12v12H9z M15 9V3H3v12h6",
  info: "M12 11v6 M12 7h.01 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  filter: "M3 5h18 M6 12h12 M9 19h6",
  trend: "M3 17l6-6 4 4 8-10 M15 5h6v6",
  book: "M12 5C8 2 3 3 3 3v17s5-1 9 2c4-3 9-2 9-2V3s-5-1-9 2Z M12 5v17",
  link: "M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2 M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2",
  menu: "M4 6h16 M4 12h16 M4 18h16",
};
export function Icon({
  name,
  size = 18,
  className = "",
}: {
  name: IconName;
  size?: number;
  className?: string;
}) {
  return (
    <svg
      className={`icon ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
