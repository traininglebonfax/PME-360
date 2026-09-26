"use client";

/**
 * Identité de l'organisation (marque blanche, V1) : nom du produit, nom court utilisé dans les libellés, slogan,
 * couleur principale (contraste contrôlé) et logo. Appliquée à l'interface, aux rapports PDF et aux e-mails ;
 * la page de connexion la reprend avec l'adresse ``/connexion?org=<identifiant>``.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { BrandMark } from "@/components/Brand";
import { Alert, Button, Card, LoadingBlock, PageHeader, TextInput } from "@/components/ui";
import { api, ApiError, errorMessage, unwrap } from "@/lib/api";
import { type Brand, palette } from "@/lib/brand";
import { ME_KEY, useMe } from "@/lib/session";

const LOGO_MAX = 150_000;

function contrastWithWhite(hex: string): number {
  const channel = (value: number) => {
    const c = value / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const luminance = 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  return 1.05 / (luminance + 0.05);
}

export default function IdentityPage() {
  const current = useQuery({ queryKey: ["branding"], queryFn: () => unwrap(api.GET("/api/v1/organization/branding")) });
  if (current.isLoading) return <LoadingBlock />;
  if (current.error) return <Alert>{errorMessage(current.error)}</Alert>;
  return <IdentityForm initial={current.data!} />;
}

function IdentityForm({ initial }: { initial: Brand }) {
  const queryClient = useQueryClient();
  const { data: me } = useMe();
  const [form, setForm] = useState<Brand>(initial);
  const [logoError, setLogoError] = useState<string | null>(null);
  const set = (patch: Partial<Brand>) => setForm({ ...form, ...patch });
  const validColor = /^#[0-9a-fA-F]{6}$/.test(form.primary_color);
  const contrast = validColor ? contrastWithWhite(form.primary_color) : 0;
  const colors = validColor ? palette(form.primary_color) : palette(initial.primary_color);
  const loginUrl = me?.organization ? `${window.location.origin}/connexion?org=${me.organization.slug}` : "";

  const save = useMutation({
    mutationFn: () =>
      unwrap(
        api.PUT("/api/v1/organization/branding", {
          body: {
            product_name: form.product_name,
            short_name: form.short_name,
            tagline: form.tagline,
            primary_color: form.primary_color,
            logo: form.logo,
          },
        }),
      ),
    onSuccess: (data) => {
      setForm(data);
      queryClient.setQueryData(["branding"], data);
      queryClient.invalidateQueries({ queryKey: ME_KEY });
    },
  });
  const errors = save.error instanceof ApiError ? save.error.fieldErrors() : {};

  const onLogo = (file: File | undefined) => {
    setLogoError(null);
    if (!file) return;
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
      setLogoError("Logo PNG, JPEG ou WebP attendu (les SVG ne sont pas acceptés).");
      return;
    }
    if (file.size > LOGO_MAX) {
      setLogoError(`Logo trop lourd (${Math.round(file.size / 1000)} Ko) : 150 Ko au plus.`);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => set({ logo: String(reader.result) });
    reader.readAsDataURL(file);
  };

  return (
    <>
      <PageHeader
        title="Identité de l'organisation"
        subtitle="Nom, couleurs et logo affichés à vos équipes et à vos PME, dans l'application, les rapports PDF et les e-mails."
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <Card>
          <form
            className="grid gap-4 sm:grid-cols-2"
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate();
            }}
          >
            <TextInput
              label="Nom du produit"
              value={form.product_name}
              maxLength={40}
              onChange={(e) => set({ product_name: e.target.value })}
              hint="Titre de l'application et de l'onglet du navigateur (défaut : PME360)."
              error={errors.product_name}
            />
            <TextInput
              label="Nom court de l'organisation"
              value={form.short_name}
              maxLength={40}
              onChange={(e) => set({ short_name: e.target.value })}
              hint="Utilisé dans les libellés : « Équipe … », « Mon conseiller … »."
              error={errors.short_name}
            />
            <div className="sm:col-span-2">
              <TextInput label="Slogan" value={form.tagline} maxLength={80} onChange={(e) => set({ tagline: e.target.value })} error={errors.tagline} />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="brand-color" className="text-sm font-medium text-ink">
                Couleur principale
              </label>
              <div className="flex items-center gap-2">
                <input
                  id="brand-color"
                  type="color"
                  aria-label="Choisir la couleur"
                  className="h-10 w-12 cursor-pointer rounded border border-line"
                  value={validColor ? form.primary_color : "#000000"}
                  onChange={(e) => set({ primary_color: e.target.value.toUpperCase() })}
                />
                <input
                  aria-label="Couleur principale (hexadécimal)"
                  className="w-28 rounded-lg border border-line px-3 py-2 font-mono text-sm"
                  value={form.primary_color}
                  maxLength={7}
                  onChange={(e) => set({ primary_color: e.target.value })}
                />
              </div>
              <p className={contrast >= 4.5 ? "text-xs text-muted" : "text-xs text-red-700"} role={contrast >= 4.5 ? undefined : "alert"}>
                {validColor
                  ? contrast >= 4.5
                    ? `Contraste avec le texte blanc : ${contrast.toFixed(1)}:1 (lisible).`
                    : `Contraste ${contrast.toFixed(1)}:1 : trop clair, le texte blanc des boutons serait illisible (4,5:1 minimum).`
                  : "Format attendu : #RRGGBB."}
              </p>
              {errors.primary_color && <p className="text-xs text-red-700">{errors.primary_color}</p>}
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="brand-logo" className="text-sm font-medium text-ink">
                Logo
              </label>
              <input id="brand-logo" type="file" accept="image/png,image/jpeg,image/webp" className="text-sm" onChange={(e) => onLogo(e.target.files?.[0])} />
              <p className="text-xs text-muted">PNG, JPEG ou WebP, 150 Ko au plus, de préférence carré.</p>
              {form.logo && (
                <button type="button" className="self-start text-xs text-red-700 hover:underline" onClick={() => set({ logo: null })}>
                  Retirer le logo
                </button>
              )}
              {(logoError || errors.logo) && <p className="text-xs text-red-700">{logoError ?? errors.logo}</p>}
            </div>
            {save.isSuccess && <Alert tone="success">Identité enregistrée : elle s'applique immédiatement.</Alert>}
            {save.error && Object.keys(errors).length === 0 && <Alert>{errorMessage(save.error)}</Alert>}
            <div className="sm:col-span-2">
              <Button type="submit" loading={save.isPending} disabled={!validColor || contrast < 4.5}>
                Enregistrer l'identité
              </Button>
            </div>
          </form>
        </Card>

        <div className="space-y-4">
          <Card title="Aperçu">
            <div className="overflow-hidden rounded-lg border border-line" data-testid="brand-preview">
              <div className="flex items-center gap-2.5 px-4 py-3 text-white" style={{ background: colors["800"] }}>
                <BrandMark className="h-8 w-8" brand={form} />
                <div className="min-w-0">
                  <p className="truncate font-semibold">{form.product_name || "PME360"}</p>
                  <p className="truncate text-xs" style={{ color: colors["100"] }}>
                    {form.short_name}
                  </p>
                </div>
              </div>
              <div className="space-y-2 bg-white p-4 text-sm">
                <p className="text-muted">Mon conseiller {form.short_name}</p>
                <span className="inline-block rounded-lg px-3 py-2 text-sm font-medium text-white" style={{ background: colors["600"] }}>
                  Bouton principal
                </span>
                <span className="ml-2 inline-block rounded-md px-2 py-0.5 text-xs" style={{ background: colors["50"], color: colors["800"] }}>
                  Étiquette
                </span>
              </div>
            </div>
          </Card>
          {loginUrl && (
            <Card title="Page de connexion à votre nom">
              <p className="text-sm text-muted">Communiquez cette adresse à vos équipes et à vos PME :</p>
              <p className="mt-2 break-all rounded-md bg-gray-50 p-2 font-mono text-xs">{loginUrl}</p>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
