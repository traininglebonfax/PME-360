export function BrandMark({ className = "h-9 w-9" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 40 40" aria-hidden="true">
      <rect width="40" height="40" rx="10" fill="#0f6b4f" />
      <circle cx="20" cy="20" r="11" fill="none" stroke="#a7f3d0" strokeWidth="3" strokeDasharray="52 17" />
      <path d="M14 22l4 4 8-10" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function BrandName({ name = "GUDE-PME 360" }: { name?: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <BrandMark />
      <div className="leading-tight">
        <p className="font-semibold text-ink">{name}</p>
        <p className="text-xs text-muted">Connaître · Accompagner · Mesurer</p>
      </div>
    </div>
  );
}
