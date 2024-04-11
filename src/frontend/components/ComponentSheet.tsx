'use client';

import { Button } from "./ui/button";
import ComponentViewer from "./ComponentViewer";
import { ComponentData } from "./models";
import { 
  Sheet, 
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger } from "./ui/sheet";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { rgbToHex } from "@/lib/utils";
import { Tooltip, TooltipProvider, TooltipTrigger, TooltipContent } from "./ui/tooltip";

export default function ComponentSheet({
  component_data,
}: {
  component_data: ComponentData
}) {

  // Component Color
  const colR = Math.round(component_data.color[0]);
  const colG = Math.round(component_data.color[1]);
  const colB = Math.round(component_data.color[2]);
  const hexcol = rgbToHex(colR, colG, colB)

  return (
    
    <Sheet>
      <SheetTrigger asChild>
        <div className='text-left align-text-top cursor-pointer'>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" className="w-[320px] hover:bg-[#009cda] hover:text-white">{component_data._id}</Button>
              </TooltipTrigger>
              <TooltipContent>
                Click to preview
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </SheetTrigger>

      <SheetContent side='bottom'>
        <SheetHeader>
          <SheetTitle className="text-center">Component Viewer</SheetTitle>
          <SheetDescription>
            <Card className="m-2">
              <CardHeader>
                <CardTitle className="text-sm text-left">{component_data._id}</CardTitle>
              </CardHeader>
              <CardContent className="text-left">
                Type: {component_data.type} <br/>
                Material: {component_data.material} <br/>
                Material Thickness: {component_data.materialthickness} <br/>
                <div className="flex items-center max-w-12">
                Color: 
                <div className="ml-2 avatar rounded-full min-h-4 min-w-4 max-w-5 max-h-5 items-center justify-left" style={{backgroundColor: hexcol}}></div>
                <div className="ml-2 items-center justify-center text-center">{colR}/{colG}/{colB}</div>
                </div>
              </CardContent>
            </Card>
          </SheetDescription>
        </SheetHeader>
            <ComponentViewer component_data={component_data}/>
        <SheetFooter>
          <div >
          <SheetClose asChild className="text-center items-center">
            <Button variant="outline">Close</Button>
          </SheetClose>
          </div>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}