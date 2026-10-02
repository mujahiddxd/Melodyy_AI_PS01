import type { ReactNode } from "react";
import { CustomerProvider } from "@/lib/customer";

export default function ShopLayout({ children }: { children: ReactNode }) {
  return <CustomerProvider>{children}</CustomerProvider>;
}
