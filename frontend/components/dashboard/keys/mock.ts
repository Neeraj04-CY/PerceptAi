export interface ApiKeyRow {
  id: string;
  name: string;
  prefix: string;     // sk_live_••••f2a1
  env: "production" | "staging" | "development";
  createdAt: string;
  lastUsed: string;
  status: "active" | "revoked";
  scopes: string[];
}

export const initialKeys: ApiKeyRow[] = [
  {
    id: "key_01HZ3R5K",
    name: "Production · primary",
    prefix: "sk_live_••••f2a1",
    env: "production",
    createdAt: "Nov 14, 2025",
    lastUsed: "2 min ago",
    status: "active",
    scopes: ["run:write", "run:read", "session:read"],
  },
  {
    id: "key_01HX1B8M",
    name: "Staging · CI runner",
    prefix: "sk_test_••••88c4",
    env: "staging",
    createdAt: "Oct 03, 2025",
    lastUsed: "1 hr ago",
    status: "active",
    scopes: ["run:write", "run:read"],
  },
  {
    id: "key_01HW0Q42",
    name: "Local dev · emil@",
    prefix: "sk_test_••••0091",
    env: "development",
    createdAt: "Sep 28, 2025",
    lastUsed: "3 days ago",
    status: "active",
    scopes: ["run:write"],
  },
  {
    id: "key_01HV4N09",
    name: "Legacy ops bot",
    prefix: "sk_live_••••71a8",
    env: "production",
    createdAt: "Aug 11, 2025",
    lastUsed: "revoked",
    status: "revoked",
    scopes: ["run:write", "run:read"],
  },
];

export function makeFreshKey(name: string) {
  const tail = Math.random().toString(36).slice(2, 6) + Math.random().toString(36).slice(2, 6);
  return `sk_live_${tail}${Math.random().toString(36).slice(2, 22)}`;
}
