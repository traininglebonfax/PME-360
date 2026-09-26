import type { Brand } from "@/lib/brand";
import { DEFAULT_BRAND } from "@/lib/brand";

/** Logo de l'organisation, ou pictogramme neutre aux couleurs de la marque. */
export function BrandMark({ className = "h-9 w-9", brand }: { className?: string; brand?: Brand }) {
  if (brand?.logo) {
    // Image embarquée (data URI) validée côté serveur : PNG, JPEG ou WebP.
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={brand.logo} alt="" className={`${className} rounded-lg bg-white object-contain p-0.5`} />;
  }
  return (
    <svg className={className} viewBox="0 0 40 40" aria-hidden="true">
      <rect width="40" height="40" rx="10" fill="var(--color-brand-600)" />
      <circle cx="20" cy="20" r="11" fill="none" stroke="var(--color-brand-200)" strokeWidth="3" strokeDasharray="52 17" />
      <path d="M14 22l4 4 8-10" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function BrandName({ brand = DEFAULT_BRAND }: { brand?: Brand }) {
  return (
    <div className="flex items-center gap-2.5">
      <BrandMark brand={brand} />
      <div className="leading-tight">
        <p className="font-semibold text-ink">{brand.product_name}</p>
        {brand.tagline && <p className="text-xs text-muted">{brand.tagline}</p>}
      </div>
    </div>
  );
}
