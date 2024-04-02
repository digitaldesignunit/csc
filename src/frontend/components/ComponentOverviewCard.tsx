'use client'

import Link from "next/link";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "./ui/card";
import { ComponentData } from "@/components/models";
import { usePathname } from "next/navigation";
import { Button } from "./ui/button";
import { useState } from "react";

export default function ComponentOverviewCard({
  params,
}: {
  params: { component_data: ComponentData };
}) {
  const [active, setActive] = useState<string>("");

  const toggleHandler = (id: string) => () =>
    setActive((active) => (active === id ? "" : id));


  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>
            {/* <Link href={`${thisPath}/${params.component_data._id}`}>
              {params.component_data._id}
            </Link> */}
            <div onClick={toggleHandler(params.component_data._id)}>
              {params.component_data._id}
              {active === params.component_data._id && <Button>Content 1</Button>}
            </div>
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