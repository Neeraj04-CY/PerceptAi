import { redirect } from "next/navigation";

// Missions are operations too: one work record at /dashboard/operations.
// Detail pages (/dashboard/missions/[id]) are unchanged.
export default function MissionsRedirect() {
  redirect("/dashboard/operations");
}
