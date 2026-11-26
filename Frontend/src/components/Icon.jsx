const paths = {
  assistant: (
    <>
      <path d="M12 3.5a8.5 8.5 0 0 0-7.1 13.18L4 21l4.33-1.35A8.5 8.5 0 1 0 12 3.5Z" />
      <path d="M8.5 12h.01M12 12h.01M15.5 12h.01" />
    </>
  ),
  book: (
    <>
      <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v17H6.5A2.5 2.5 0 0 1 4 17.5z" />
      <path d="M4 16.5A2.5 2.5 0 0 1 6.5 14H20M8 7h7M8 10h7" />
    </>
  ),
  check: <path d="m5 12 4 4L19 6" />,
  chevron: <path d="m9 18 6-6-6-6" />,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  filter: (
    <>
      <path d="M4 7h16M7 12h10m-7 5h4" />
      <circle cx="8" cy="7" r="1.5" /><circle cx="15" cy="12" r="1.5" />
    </>
  ),
  graduation: (
    <>
      <path d="m2.5 9 9.5-5 9.5 5-9.5 5z" />
      <path d="M6 11v5c3.5 3 8.5 3 12 0v-5M21.5 9v6" />
    </>
  ),
  login: (
    <>
      <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
      <polyline points="10 17 15 12 10 7" />
      <line x1="15" y1="12" x2="3" y2="12" />
    </>
  ),
  logout: (
    <>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </>
  ),
  home: (
    <>
      <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z" />
    </>
  ),
  microphone: (
    <>
      <rect x="9" y="2.5" width="6" height="12" rx="3" />
      <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3.5M9 21.5h6" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 7v5h-5" />
      <path d="M20 12a8 8 0 1 1-2.34-5.66L20 9" />
    </>
  ),
  search: (
    <>
      <circle cx="10.8" cy="10.8" r="6.8" />
      <path d="m16 16 4.5 4.5" />
    </>
  ),
  send: (
    <>
      <path d="m22 2-7 20-4-9-9-4z" />
      <path d="M22 2 11 13" />
    </>
  ),
  scholarship: (
    <>
      <path d="M5 4h14a2 2 0 0 1 2 2v14H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" />
      <path d="M7 4v6l3-2 3 2V4M7 14h10m-10 3h7" />
    </>
  ),
  spark: (
    <>
      <path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />
      <path d="m19 15 .9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z" />
    </>
  ),
  speaker: (
    <>
      <path d="M4 10v4h4l5 4V6l-5 4H4Z" />
      <path d="M17 9a5 5 0 0 1 0 6m2.5-8.5a8.5 8.5 0 0 1 0 11" />
    </>
  ),
  stop: <rect x="6" y="6" width="12" height="12" rx="2" />,
  user: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21a8 8 0 0 1 16 0" />
    </>
  ),
};

export default function Icon({ name, size = 20, className = "" }) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name] || paths.scholarship}
    </svg>
  );
}
