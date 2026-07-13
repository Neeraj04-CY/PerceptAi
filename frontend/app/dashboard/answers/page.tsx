import { redirect } from "next/navigation";

// Answers grew into Knowledge — organizational intelligence, one page.
export default function AnswersRedirect() {
  redirect("/dashboard/knowledge");
}
