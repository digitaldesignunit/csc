import { ComponentOverviewDataTable } from "@/components/ComponentOverviewDataTable";
import ComponentOverviewPagination from "@/components/ComponentOverviewPagination";
import { ComponentData } from "@/components/models";
import { ComponentOverviewColumns } from "@/components/ComponentOverviewColumns";
import { Card } from "@/components/ui/card";
import { diff_mins } from "@/lib/utils";

let API_TOKEN: string = '';
let API_TOKENTIME: string = '2024-04-06T06:38:20.567Z';

const create_headers = async (token: string) => {
  const tokenmins = Number(process.env.API_TOKEN_TIMEOUT_MINS)
  let tokentime = diff_mins(new Date(API_TOKENTIME as string), new Date())
  console.log(`Current tokentime is ${tokentime} minutes`)
  if (!token || !API_TOKEN) {
    token = await fetch_token();
    API_TOKEN = token
    API_TOKENTIME = new Date().toString()
  } else if (tokentime >= tokenmins){
    token = await fetch_token();
    API_TOKEN = token
    // set tokentime to now
    API_TOKENTIME = new Date().toString()
  }
  return {'Authorization': `Bearer ${token}`}
}

const fetch_token = async () => {
  const token_url = process.env.API_TOKEN_URL as string;
  const username = process.env.API_USER as string;
  const password = process.env.API_PASS as string;
  // create headers
  let form_data = new URLSearchParams({
    'grant_type': 'password',
    'username': username,
    'password': password
  })
  // execute fetch
  let tokendata = await fetch(
    token_url,
    {
      method: 'POST',
      mode: 'cors',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: form_data.toString()
    }
  ).then((response) => {
    console.log(`Fetch Token Response Status: ${response.status}`)
    let data = response.json()
    API_TOKENTIME = new Date().toString()
    return data
  }).catch((err) => {
    console.log('Fetch Token Response Rejected!')
    console.log(err)
    return ''
  })
  let token = await tokendata.access_token
  return token
}

const fetch_components = async (page_num: Number, page_size: Number, retried: boolean = false) => {
  const endpoint_url = `https://api.ddu.uber.space/components?page=${page_num}&size=${page_size}`
  let headers = await create_headers(API_TOKEN)
  let components: Array<ComponentData> = await fetch(
    endpoint_url,
    {
      method: 'GET',
      mode: 'cors',
      headers: headers
    }
  ).then(async response => {
    console.log(`Get Components Response Status: ${response.status}`)
    if (response.status == 401 && !retried) {
      console.log('Response Unauthorized! Attempting Retry...')
      API_TOKEN = await fetch_token()
      return fetch_components(page_num, page_size, true)
    }
    return response.json()
  }).catch((err) => {
    if (!retried) {
      console.log('Get Components Response Rejected!')
      console.log(err)
      console.log('Attempting retry...')
      return fetch_components(page_num, page_size, true)
    } else {
      console.log('Get Components 2nd Response Rejected! Aborting...')
      console.log(err)
      return []
    }
  });
  return components
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
  let page = Number(searchParams?.page) || 1;
  let size = Number(searchParams?.size) || 10;

  // fetch components from API using search params
  let db_components = await fetch_components(page, size)

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
