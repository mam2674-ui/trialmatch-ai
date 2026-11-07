import type { Metadata } from "next";

export const metadata: Metadata = { title: "Compare studies" };

export default function Layout({ children }: LayoutProps<"/compare">) {
  return children;
}
