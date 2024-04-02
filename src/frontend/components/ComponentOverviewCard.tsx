'use client'

import Link from "next/link";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "./ui/card";
import { ComponentData } from "@/components/models";
import { usePathname } from "next/navigation";

export default function ComponentOverviewCard({
  params,
}: {
  params: { component_data: ComponentData };
}) {
  const thisPath = usePathname();

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>
            <Link href={`${thisPath}/${params.component_data._id}`}>
              {params.component_data._id}
            </Link>
          </CardTitle>
          <CardDescription>{params.component_data.type}</CardDescription>
        </CardHeader>
        <CardContent>
          Geometry here
        </CardContent>
        <CardFooter>
          <p>Card Footer</p>
        </CardFooter>
      </Card>
    </>
  );
}