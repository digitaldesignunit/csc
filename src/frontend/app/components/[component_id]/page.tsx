import ComponentDetailCard from "@/components/ComponentDetailCard";

export default function ComponentDetails({
  params,
}: {
  params: { component_id: string };
}) {
  return (
    <div>
      <ComponentDetailCard params={{component_id: params.component_id}}/>
    </div>
  );
}
