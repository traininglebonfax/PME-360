import { GudeShell } from "@/components/AppShell";

export default function GudeLayout({ children }: { children: React.ReactNode }) {
  return <GudeShell>{children}</GudeShell>;
}
