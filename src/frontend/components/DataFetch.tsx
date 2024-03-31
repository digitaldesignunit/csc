'use client';

import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "./ui/card";

// Fetch data from api using async function
export default async function DataFetch() {
  const getAllComponents = async () => {
    const res = await fetch('https://api.ddu.uber.space/')
    return res.json()
}


  const comps = await getAllComponents()

  return (
    <div className="grow">
      <h1>Database Components</h1>
      <div>
        <ul>
          {comps.map( (comp: any) => 
            <li key={comp._id}>
              <Card>
                <CardHeader>
                  <CardTitle>{comp._id}</CardTitle>
                  <CardDescription>{comp.type}</CardDescription>
                </CardHeader>
                <CardContent>
                  Geometry here
                </CardContent>
                <CardFooter>
                  <p>Card Footer</p>
                </CardFooter>
              </Card>
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}