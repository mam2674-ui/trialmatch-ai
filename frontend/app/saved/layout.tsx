import type { Metadata } from "next";

export const metadata: Metadata = { title: "Saved studies" };

export default function Layout({ children }: LayoutProps<"/saved">) {
  return children;
}
