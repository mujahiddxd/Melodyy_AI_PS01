// Label for any mocked feature. Required by the project rules ("DEMO / MOCK").
export function MockBadge({ children = "DEMO / MOCK" }: { children?: string }) {
  return <span className="badge border-2 border-ink bg-butter">{children}</span>;
}
