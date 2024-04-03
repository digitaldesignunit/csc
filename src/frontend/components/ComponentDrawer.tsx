'use client';

import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from "@/components/ui/drawer"
import { Button } from "./ui/button";
import ComponentViewer from "./ComponentViewer";
import { ComponentData } from "./models";

export default function ComponentDrawer({
  component_data,
}: {
  component_data: ComponentData
}) {

  return (
    
    <Drawer>
      <DrawerTrigger asChild>
      <div className='text-left align-text-top font-bold cursor-pointer'>
        
      
        <Button variant="outline">{component_data._id}</Button>
        </div>
      </DrawerTrigger>

      <DrawerContent >
        <DrawerHeader>
          <DrawerTitle>Component Viewer</DrawerTitle>
          <DrawerDescription>
            <b>ID: {component_data._id} </b><br/>
            Type: {component_data.type} <br/>
            Material: {component_data.material} <br/>
            Material Thickness: {component_data.materialthickness} <br/>
            Color: {component_data.color}
          </DrawerDescription>
        </DrawerHeader>
          <div data-vaul-no-drag>
            <ComponentViewer component_data={component_data}/>
          </div>
        <DrawerFooter>
          <DrawerClose asChild>
            <Button variant="outline">Close</Button>
          </DrawerClose>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}