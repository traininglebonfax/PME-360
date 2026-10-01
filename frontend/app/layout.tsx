import type { Metadata, Viewport } from "next";

import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: { default: "PME360", template: "%s · PME360" },
  description: "Diagnostic 360°, scoring, accompagnement et pilotage des PME.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#2e4a6b" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr" suppressHydrationWarning>
      {/* Certaines extensions de navigateur ajoutent des attributs à <html>/<body> avant l'hydratation. */}
      <body suppressHydrationWarning>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
