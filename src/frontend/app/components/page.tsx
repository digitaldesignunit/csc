import { ComponentOverviewDataTable } from "@/components/ComponentOverviewDataTable";
import ComponentOverviewPagination from "@/components/ComponentOverviewPagination";
import { ComponentData } from "@/components/models";
import { ComponentOverviewColumns } from "@/components/ComponentOverviewColumns";

export default async function Components({
  searchParams,
}: {
  searchParams?: {
    page?: string;
    limit?: string;
  };
}) {

  const pageNum = Number(searchParams?.page) || 1;
  const pageSize = Number(searchParams?.limit) || 10;

  const fetchComponentData = async () => {
    const response = await fetch(`https://api.ddu.uber.space/components?page=${pageNum}&size=${pageSize}`)
    const items: Array<ComponentData> = await response.json();
    return items;
  }

  const comps = await fetchComponentData()

  return (
    <>
      <div className="container mx-auto py-10">
        <ComponentOverviewDataTable columns={ComponentOverviewColumns} data={comps} />
      </div>

      {/* <div className="grow">
        <h1>Database Components</h1>
        <div>
          <ul>
            {comps.map( (comp_item) => 
              <li key={comp_item._id}>
                <ComponentOverviewCard params={{component_data: comp_item}} />
              </li>
            )}
          </ul>
        </div>
      </div> */}

      <div>
        <ComponentOverviewPagination pageNum={pageNum} pageSize={pageSize}/>
      </div>
    </>
  );
}
