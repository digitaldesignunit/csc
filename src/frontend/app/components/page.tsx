import { ComponentOverviewDataTable } from "@/components/ComponentOverviewDataTable";
import ComponentOverviewPagination from "@/components/ComponentOverviewPagination";
import { ComponentData } from "@/components/models";
import { ComponentOverviewColumns } from "@/components/ComponentOverviewColumns";
import { Card } from "@/components/ui/card";

export default async function ComponentsPage({
  searchParams,
}: {
  searchParams?: {
    page?: string;
    size?: string;
  };
}) {

  const pageNum = Number(searchParams?.page) || 1;
  const pageSize = Number(searchParams?.size) || 10;

  const fetchComponentData = async () => {
    const response = await fetch(`https://api.ddu.uber.space/components?page=${pageNum}&size=${pageSize}`)
    const items: Array<ComponentData> = await response.json();
    return items;
  }

  const comps = await fetchComponentData()

  return (
    <>
      <div className="grid gap-[32px] m-4">
        <Card>
          <ComponentOverviewDataTable columns={ComponentOverviewColumns} data={comps} />
        </Card>
        <ComponentOverviewPagination pageNum={pageNum} pageSize={pageSize}/>
      </div>

      <div>
        
      </div>
    </>
  );
}
