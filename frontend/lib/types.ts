// Shared API types. Keep in sync with /API_CONTRACT.md.

export interface Health {
  status: "ok" | "degraded";
  db: "ok" | "error";
}
