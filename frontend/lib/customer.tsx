"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError, CUSTOMER_AUTH_EVENT, getToken, setToken } from "./api";
import type { Customer } from "./types";

// Customer session. Browsing never needs it; only verified customers have a customer_token.
interface CustomerState {
  customer: Customer | null;
  loading: boolean;
  signIn: (token: string, customer: Customer) => void;
  logout: () => void;
}

const Ctx = createContext<CustomerState | null>(null);

export function CustomerProvider({ children }: { children: ReactNode }) {
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!getToken("customer")) {
      setCustomer(null);
      setLoading(false);
      return;
    }
    try {
      setCustomer(await api<Customer>("/customer/me", { role: "customer" }));
    } catch (e) {
      // 401 already cleared the token; any other error: stay a guest for now
      if (!(e instanceof ApiError && e.status === 401)) setCustomer(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const onChange = () => load();
    window.addEventListener(CUSTOMER_AUTH_EVENT, onChange);
    return () => window.removeEventListener(CUSTOMER_AUTH_EVENT, onChange);
  }, [load]);

  const signIn = useCallback((token: string, c: Customer) => {
    setToken("customer", token);
    setCustomer(c);
  }, []);

  const logout = useCallback(() => {
    setToken("customer", null);
    setCustomer(null);
  }, []);

  const value = useMemo(() => ({ customer, loading, signIn, logout }), [customer, loading, signIn, logout]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCustomer(): CustomerState {
  const c = useContext(Ctx);
  if (!c) throw new Error("useCustomer must be used inside <CustomerProvider>");
  return c;
}
