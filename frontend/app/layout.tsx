import type { Metadata, Viewport } from "next";

import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: { default: "GUDE-PME 360", template: "%s · GUDE-PME 360" },
  description: "Diagnostic 360°, scoring, accompagnement et pilotage des PME.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#0f6b4f" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
