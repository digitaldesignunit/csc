import ComponentOverviewCard from "@/components/ComponentOverviewCard";
import ComponentOverviewPagination from "@/components/ComponentOverviewPagination";
import { ComponentData } from "@/components/models";

export default async function ComponentOverview() {

  const pageNum = 1;
  const pageSize = 10;

  const fetchComponentData = async () => {
    const response = await fetch(`https://api.ddu.uber.space/components?page=${pageNum}&size=${pageSize}`)
    const items: Array<ComponentData> = await response.json();
    return items;
  }

  const comps = await fetchComponentData()

  return (
    <>
      <div className="grow">
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
      </div>

      <div>
        <ComponentOverviewPagination />
      </div>
    </>
  );
}
