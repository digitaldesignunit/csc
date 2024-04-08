import { ComponentOverviewDataTable } from "@/components/ComponentOverviewDataTable";
import ComponentOverviewPagination from "@/components/ComponentOverviewPagination";
import { ComponentData } from "@/components/models";
import { ComponentOverviewColumns } from "@/components/ComponentOverviewColumns";
import { Card } from "@/components/ui/card";
import { diff_mins } from "@/lib/utils";

const create_headers = async (token: string) => {
  if (!token || !process.env.API_TOKENTIME) {
    const token_response = await fetch_token();
    token = token_response.access_token
    process.env.API_TOKEN = token
    process.env.API_TOKENTIME = new Date().toString()
  } else if (diff_mins(new Date(process.env.API_TOKENTIME as string), new Date()) >= Number(process.env.API_TOKEN_TIMEOUT_MINS)){
    const token_response = await fetch_token();
    token = token_response.access_token
    process.env.API_TOKEN = token
    // set tokentime to now
    process.env.API_TOKENTIME = new Date().toString()
  }
  return {'Authorization': `Bearer ${token}`}
}

const fetch_token = async () => {
  const token_url = process.env.API_TOKEN_URL as string;
  const username = process.env.API_USER as string;
  const password = process.env.API_PASS as string;
  // create headers
  const form_data = new URLSearchParams({
    'grant_type': 'password',
    'username': username,
    'password': password
  })
  // execute fetch
  const response = await fetch(
    token_url,
    {
      method: 'POST',
      mode: 'cors',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: form_data.toString()
    }
  )
  // check response and return if okay
  if (response.ok) {
    console.log(`Fetch Token Response Status: ${response.status}`)
  } else {
    console.log(`Response failed, Status: ${response.status}`);
  }
  // return json response
  const json_response = await response.json()
  return json_response
}

const fetch_components = async (page_num: Number, page_size: Number) => {
  const endpoint_url = `https://api.ddu.uber.space/component?page=${page_num}&size=${page_size}`
  const headers = await create_headers(process.env.API_TOKEN as string)
  const response = await fetch(
    endpoint_url,
    {
      method: 'GET',
      mode: 'cors',
      headers: headers
    }
  )
  // check response and return if okay
  if (response.ok) {
    console.log(`Get Components Response Status: ${response.status}`)
    const components: Array<ComponentData> = await response.json();
    return components
  } else if (response.status == 401) {
    console.log(`Response Unauthorized, Status: ${response.status}`);
    console.log('Acquiring new token...')
    const new_headers = await create_headers('')
    const retry_response = await fetch(
      endpoint_url,
      {
        method: 'GET',
        mode: 'cors',
        headers: new_headers
      }
    )
    if (retry_response.ok) {
      console.log(`Get Components 2nd Response Status: ${response.status}`)
      const components: Array<ComponentData> = await response.json();
      return components
    } else {
      console.log(`Response failed, Status: ${response.status}`);
      return null
    }
  }
}

export default async function ComponentsPage({
  searchParams,
}: {
  searchParams?: {
    page?: string;
    size?: string;
  };
}) {
  // search params retrieval
  const page = Number(searchParams?.page) || 1;
  const size = Number(searchParams?.size) || 10;

  // fetch components from API using search params
  const db_components = await fetch_components(page, size)

  return (
    <>
      <div className="grid gap-[32px] m-4">
        <Card>
          <ComponentOverviewDataTable columns={ComponentOverviewColumns} data={db_components as ComponentData[]} />
        </Card>
        <ComponentOverviewPagination pageNum={page} pageSize={size}/>
      </div>
    </>
  );
}
