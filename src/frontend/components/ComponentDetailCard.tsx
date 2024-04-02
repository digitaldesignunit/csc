'use client'

import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "./ui/card";

export default function ComponentDetailCard({
  params,
}: {
  params: { component_id: string };
}) {
  return (
    <div>
      <Card>
        <CardHeader>
          <CardTitle>
            {params.component_id}
          </CardTitle>
          <CardDescription>Description</CardDescription>
        </CardHeader>
        <CardContent>
          Geometry here
        </CardContent>
        <CardFooter>
          <p>Card Footer</p>
        </CardFooter>
      </Card>
    </div>
  );
}