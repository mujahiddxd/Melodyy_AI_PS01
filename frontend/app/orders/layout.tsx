import type { ReactNode } from "react";
import { CustomerProvider } from "@/lib/customer";

export default function OrdersLayout({ children }: { children: ReactNode }) {
  return <CustomerProvider>{children}</CustomerProvider>;
}
