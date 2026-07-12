import { redirect } from "next/navigation";

// Sessions lives on as the work record: /dashboard/operations.
// Detail pages (/dashboard/sessions/[id]) are unchanged.
export default function SessionsRedirect() {
  redirect("/dashboard/operations");
}
