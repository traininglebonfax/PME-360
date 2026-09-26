/** Composants d'interface de base : sobres, accessibles, lisibles sur mobile (Document 1, § 10). */
import Link from "next/link";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, Ref, SelectHTMLAttributes } from "react";
import { useId } from "react";

function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-brand-600 text-white hover:bg-brand-700 disabled:bg-brand-600/50",
  secondary: "bg-white text-ink border border-line hover:bg-gray-50 disabled:text-muted",
  ghost: "text-brand-700 hover:bg-brand-50",
  danger: "bg-red-600 text-white hover:bg-red-700",
};

export function Button({
  variant = "primary",
  loading = false,
  className,
  children,
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; loading?: boolean }) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors disabled:cursor-not-allowed",
        VARIANTS[variant],
        className,
      )}
    >
      {loading && <Spinner className="h-4 w-4" />}
      {children}
    </button>
  );
}

export function ButtonLink({ href, children, variant = "primary" }: { href: string; children: ReactNode; variant?: Variant }) {
  return (
    <Link
      href={href}
      className={cx("inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium", VARIANTS[variant])}
    >
      {children}
    </Link>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={cx("animate-spin", className ?? "h-5 w-5")} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="4" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}

export function Card({ title, action, children, className }: { title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("rounded-xl border border-line bg-surface p-5 shadow-sm", className)}>
      {(title || action) && (
        <header className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="text-base font-semibold text-ink">{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

type FieldProps = { label: string; error?: string; hint?: string; required?: boolean };

export function Field({ label, error, hint, required, children, id }: FieldProps & { children: ReactNode; id: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
        {required && <span className="text-red-600"> *</span>}
      </label>
      {children}
      {hint && !error && <p className="text-xs text-muted">{hint}</p>}
      {error && (
        <p className="text-xs text-red-700" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

const CONTROL =
  "w-full rounded-lg border bg-white px-3 py-2.5 text-sm text-ink placeholder:text-gray-400 focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-100";

export function TextInput({
  label,
  error,
  hint,
  required,
  className,
  ...props
}: FieldProps & InputHTMLAttributes<HTMLInputElement> & { ref?: Ref<HTMLInputElement> }) {
  const id = useId();
  return (
    <Field label={label} error={error} hint={hint} required={required} id={id}>
      <input
        id={id}
        required={required}
        aria-invalid={Boolean(error)}
        className={cx(CONTROL, error ? "border-red-400" : "border-line", className)}
        {...props}
      />
    </Field>
  );
}

export function SelectInput({
  label,
  error,
  hint,
  required,
  options,
  placeholder = "— Choisir —",
  ...props
}: FieldProps & SelectHTMLAttributes<HTMLSelectElement> & { options: { value: string; label: string }[]; placeholder?: string }) {
  const id = useId();
  return (
    <Field label={label} error={error} hint={hint} required={required} id={id}>
      <select id={id} required={required} aria-invalid={Boolean(error)} className={cx(CONTROL, error ? "border-red-400" : "border-line")} {...props}>
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </Field>
  );
}

type Tone = "neutral" | "info" | "brand" | "warning" | "danger" | "muted";

const TONES: Record<Tone, string> = {
  neutral: "bg-gray-100 text-gray-700",
  info: "bg-sky-50 text-sky-800",
  brand: "bg-brand-50 text-brand-800",
  warning: "bg-amber-50 text-amber-800",
  danger: "bg-red-50 text-red-800",
  muted: "bg-gray-50 text-gray-500",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={cx("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium", TONES[tone])}>{children}</span>;
}

export function Alert({ tone = "danger", title, children }: { tone?: "danger" | "warning" | "info" | "success"; title?: string; children?: ReactNode }) {
  const styles = {
    danger: "border-red-200 bg-red-50 text-red-800",
    warning: "border-amber-200 bg-amber-50 text-amber-900",
    info: "border-sky-200 bg-sky-50 text-sky-900",
    success: "border-brand-200 bg-brand-50 text-brand-800",
  }[tone];
  return (
    <div className={cx("rounded-lg border px-4 py-3 text-sm", styles)} role={tone === "danger" ? "alert" : "status"}>
      {title && <p className="font-medium">{title}</p>}
      {children && <div className={title ? "mt-1" : ""}>{children}</div>}
    </div>
  );
}

export function Kpi({ label, value, hint, definition }: { label: string; value: ReactNode; hint?: ReactNode; definition?: string }) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4 shadow-sm">
      <p className="flex items-start justify-between gap-2 text-xs font-medium uppercase tracking-wide text-muted">
        <span>{label}</span>
        {definition && (
          <span
            tabIndex={0}
            role="img"
            aria-label={`Définition : ${definition}`}
            title={definition}
            className="inline-flex h-4 w-4 shrink-0 cursor-help items-center justify-center rounded-full border border-line text-[10px] normal-case text-muted"
          >
            i
          </span>
        )}
      </p>
      <p className="mt-2 text-2xl font-semibold text-ink">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

/** Indicateur prévu mais pas encore alimenté : jamais de chiffre inventé (Document 9, § 1). */
export function PendingKpi({ label, phase }: { label: string; phase: number }) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-white/60 p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
      <p className="mt-2 text-sm text-muted">Disponible en phase {phase}</p>
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-line bg-white px-6 py-12 text-center">
      <p className="font-medium text-ink">{title}</p>
      {children && <div className="mt-1 max-w-md text-sm text-muted">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function LoadingBlock({ label = "Chargement…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted" role="status">
      <Spinner /> {label}
    </div>
  );
}

export { cx };
