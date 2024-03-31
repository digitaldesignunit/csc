export default function ComponentDetails({
  params,
}: {
  params: { component_id: string };
}) {
  return (
    <div>
      <h1>This is the component details page of {params.component_id}</h1>
    </div>
  );
}
