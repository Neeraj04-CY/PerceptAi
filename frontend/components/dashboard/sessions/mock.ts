import type { Status } from "@/components/dashboard/status-pill";

export interface SessionRow {
  id: string;
  instruction: string;
  status: Status;
  duration: string;
  steps: string; // "7 / 7"
  apiKey: string;
  region: string;
  startedAgo: string;
}

export const sessions: SessionRow[] = [
  {
    id: "run_8f2a3c7b91",
    instruction: "Open Spotify and play a jazz playlist",
    status: "completed",
    duration: "4.82s",
    steps: "7 / 7",
    apiKey: "sk_live_••••f2a1",
    region: "us-west-2",
    startedAgo: "2 min ago",
  },
  {
    id: "run_71b094aac3",
    instruction: "Launch Chrome and summarize the latest AI news",
    status: "running",
    duration: "12.3s",
    steps: "4 / 7",
    apiKey: "sk_live_••••f2a1",
    region: "us-west-2",
    startedAgo: "12 sec ago",
  },
  {
    id: "run_a04ef2c811",
    instruction: "Navigate legacy ERP dashboard and export today's invoices",
    status: "completed",
    duration: "23.41s",
    steps: "12 / 12",
    apiKey: "sk_live_••••f2a1",
    region: "eu-central-1",
    startedAgo: "8 min ago",
  },
  {
    id: "run_3ee21770a4",
    instruction: "Schedule a 30-min sync with the design team in Calendar",
    status: "failed",
    duration: "6.10s",
    steps: "3 / 6",
    apiKey: "sk_test_••••88c4",
    region: "us-east-1",
    startedAgo: "14 min ago",
  },
  {
    id: "run_55a02bb9f0",
    instruction: "Reconcile yesterday's Stripe payouts with bank ledger",
    status: "completed",
    duration: "31.07s",
    steps: "18 / 18",
    apiKey: "sk_live_••••f2a1",
    region: "us-west-2",
    startedAgo: "26 min ago",
  },
  {
    id: "run_22c108b39e",
    instruction: "Triage unread support tickets by urgency",
    status: "completed",
    duration: "8.92s",
    steps: "9 / 9",
    apiKey: "sk_live_••••f2a1",
    region: "us-east-1",
    startedAgo: "41 min ago",
  },
  {
    id: "run_91fae00721",
    instruction: "Open LinkedIn and connect with last week's prospects",
    status: "queued",
    duration: "—",
    steps: "0 / —",
    apiKey: "sk_test_••••88c4",
    region: "us-west-2",
    startedAgo: "queued",
  },
  {
    id: "run_d7c2200158",
    instruction: "Export Q4 OKR dashboard as PDF and email to leadership",
    status: "completed",
    duration: "11.66s",
    steps: "8 / 8",
    apiKey: "sk_live_••••f2a1",
    region: "us-west-2",
    startedAgo: "1 hr ago",
  },
  {
    id: "run_b1409ff80c",
    instruction: "Audit GitHub PRs older than 7 days and ping reviewers",
    status: "failed",
    duration: "2.84s",
    steps: "2 / —",
    apiKey: "sk_test_••••0091",
    region: "eu-central-1",
    startedAgo: "2 hr ago",
  },
  {
    id: "run_6a8feb44e2",
    instruction: "Pull weekly cohort retention from Mixpanel",
    status: "completed",
    duration: "5.31s",
    steps: "5 / 5",
    apiKey: "sk_live_••••f2a1",
    region: "us-west-2",
    startedAgo: "3 hr ago",
  },
  {
    id: "run_4f8a911cad",
    instruction: "Fill onboarding forms for 24 new customers",
    status: "completed",
    duration: "1m 12.4s",
    steps: "48 / 48",
    apiKey: "sk_live_••••f2a1",
    region: "us-east-1",
    startedAgo: "5 hr ago",
  },
  {
    id: "run_99e21cb70f",
    instruction: "Refresh BI dashboards from updated warehouse views",
    status: "completed",
    duration: "9.18s",
    steps: "11 / 11",
    apiKey: "sk_live_••••f2a1",
    region: "us-west-2",
    startedAgo: "yesterday",
  },
];
