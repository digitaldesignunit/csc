import { ComponentOverviewDataTable } from "@/components/ComponentOverviewDataTable";
import ComponentOverviewPagination from "@/components/ComponentOverviewPagination";
import { ComponentData } from "@/components/models";
import { ComponentOverviewColumns } from "@/components/ComponentOverviewColumns";
import { Card } from "@/components/ui/card";
import { diff_mins } from "@/lib/utils";

let API_TOKEN: string = '';
let API_TOKENTIME: string = '2024-04-06T06:38:20.567Z';
let API_TIMEOUT_MINS = Number(process.env.API_TOKEN_TIMEOUT_MINS)
const API_TOKEN_URL: string = process.env.API_TOKEN_URL as string;
const API_USER: string = process.env.API_USER as string;
const API_PASS: string = process.env.API_PASS as string;

const create_headers = async (token: string) => {
  const tokenmins = API_TIMEOUT_MINS
  let tokentime = diff_mins(new Date(API_TOKENTIME as string), new Date())
  console.log(`Current tokentime is ${tokentime} minutes`)
  // console.log('Current token is:')
  // console.log(token)
  if (!token || !API_TOKEN) {
    console.log('No Token present. Acquiring token...')
    token = await fetch_token();
    API_TOKEN = token
    API_TOKENTIME = new Date().toString()
  } else if (tokentime >= tokenmins){
    console.log('Token expired. Acquiring new token...')
    token = await fetch_token();
    API_TOKEN = token
    // set tokentime to now
    API_TOKENTIME = new Date().toString()
    // console.log('Token is:')
    // console.log(token)
  }
  // console.log('Token is:')
  // console.log(token)
  return {'Authorization': `Bearer ${token}`}
}

const fetch_token = async () => {
  const token_url: string = API_TOKEN_URL
  const username: string = API_USER
  const password: string = API_PASS
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
      body: form_data.toString(),
      cache: 'no-store'
    }
  ).then(async (response) => {
    console.log(`Fetch Token Response Status: ${response.status}`)
    let data = await response.json()
    API_TOKENTIME = new Date().toString()
    return data
  }).catch((err) => {
    console.log('Fetch Token Response Rejected! Aborting...')
    console.log(err)
    return ''
  })
  let token = await tokendata.access_token
  return token
}

const fetch_components = async (page_num: Number, page_size: Number, retried: boolean = false) => {
  const endpoint_url = `https://api.ddu.uber.space/components?page=${page_num}&size=${page_size}`
  // console.log(endpoint_url)
  let headers = await create_headers(API_TOKEN)
  let components: Array<ComponentData> = await fetch(
    endpoint_url,
    {
      method: 'GET',
      mode: 'cors',
      headers: headers,
      cache: 'no-store'
    }
  ).then( async (response) => {
    console.log(`Get Components Response Status: ${response.status}`)
    if (response.status == 401 && !retried) {
      console.log('Response Unauthorized! Attempting Retry...')
      return await fetch_components(page_num, page_size, true)
    }
    return response.json()
  }).catch(async (err) => {
    if (!retried) {
      console.log('Get Components Response Rejected!')
      console.log(`Error: ${err}`)
      console.log('Attempting retry...')
      return await fetch_components(page_num, page_size, true)
    } else {
      console.log('Get Components 2nd Response Rejected! Aborting...')
      console.log(`Error: ${err}`)
      return []
    }
  });
  return components
}

const fetch_componentcount = async (retried: boolean = false) => {
  const endpoint_url = 'https://api.ddu.uber.space/componentcount'
  let headers = await create_headers(API_TOKEN)
  let count: Number = await fetch(
    endpoint_url,
    {
      method: 'GET',
      mode: 'cors',
      headers: headers,
      cache: 'no-store'
    }
  ).then( async (response) => {
    console.log(`Component Count Response Status: ${response.status}`)
    if (response.status == 401 && !retried) {
      console.log('Response Unauthorized! Attempting Retry...')
      return await fetch_componentcount(true)
    }
    return response.json()
  }).catch(async (err) => {
    if (!retried) {
      console.log('Component Count Response Rejected!')
      console.log(`Error: ${err}`)
      console.log('Attempting retry...')
      return await fetch_componentcount(true)
    } else {
      console.log('Component Count 2nd Response Rejected! Aborting...')
      console.log(`Error: ${err}`)
      return []
    }
  });
  return count
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
