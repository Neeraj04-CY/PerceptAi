import { DetailView } from "@/components/dashboard/sessions/detail/detail-view";

export default function SessionDetailPage({ params }: { params: { id: string } }) {
  return <DetailView id={params.id} />;
}
