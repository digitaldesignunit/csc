import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"
import { ComponentBoundingBox, ComponentLocation } from "@/generated/ComponentModel";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function diff_mins(dt1: Date, dt2: Date) {
  // Calculate the difference in milliseconds between the two provided dates and convert it to seconds
  let diff =(dt2.getTime() - dt1.getTime()) / 1000;
  // Convert the difference from seconds to minutes
  diff /= 60;
  // Return the absolute value of the rounded difference in minutes
  return Math.abs(Math.round(diff));
}

export function rgbToHex(r: number, g: number, b: number) {
  return (
    "#" + ((1<<24) + (r<<16) + (g<<8)+ b).toString(16).slice(1)
  );
}

export function hexComponentColor(component_color_rgb: number[]) {
    // Component Color
    const colR = Math.round(component_color_rgb[0])
    const colG = Math.round(component_color_rgb[1])
    const colB = Math.round(component_color_rgb[2])
    const hexcol = rgbToHex(colR, colG, colB)
    return hexcol
}

export function componentColorString(component_color_rgb: number[]) {
  const colR = Math.round(component_color_rgb[0])
  const colG = Math.round(component_color_rgb[1])
  const colB = Math.round(component_color_rgb[2])
  return `${colR}/${colG}/${colB}`
}

export function padZero(str: string, len: number = 2) {
  len = len || 2;
  const zeros = new Array(len).join('0');
  return (zeros + str).slice(-len);
}

export function invertColor(hex: string, bw: boolean = true) {
  if (hex.indexOf('#') === 0) {
      hex = hex.slice(1);
  }
  // convert 3-digit hex to 6-digits.
  if (hex.length === 3) {
      hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
  }
  if (hex.length !== 6) {
      throw new Error('Invalid HEX color.');
  }
  const rnum = parseInt(hex.slice(0, 2), 16)
  const gnum = parseInt(hex.slice(2, 4), 16)
  const bnum = parseInt(hex.slice(4, 6), 16)
  if (bw) {
      // https://stackoverflow.com/a/3943023/112731
      return (rnum * 0.299 + gnum * 0.587 + bnum * 0.114) > 186
          ? '#000000'
          : '#FFFFFF';
  }
  // invert color components
  const r = (255 - rnum).toString(16);
  const g = (255 - gnum).toString(16);
  const b = (255 - bnum).toString(16);
  // pad each with zeros and return
  return "#" + padZero(r) + padZero(g) + padZero(b);
}

export function timestamp_string() {
  return new Date().toISOString().replace(/T/, ' ').replace(/\..+/, '');
}

export function copyright_year() {
  const year = new Date().getFullYear()
  if (year === 2024) {
    return '2024'
  }
  return `2024 - ${year}`
}

export function combinePath(baseUrl: string, filename: string, extension: string): string {
  // Ensure the baseUrl ends with a slash
  if (!baseUrl.endsWith('/')) {
      baseUrl += '/';
  }

  // Ensure the filename does not start with a slash
  if (filename.startsWith('/')) {
      filename = filename.substring(1);
  }

  // Ensure the extension starts with a dot
  if (!extension.startsWith('.')) {
      extension = '.' + extension;
  }

  return `${baseUrl}${filename}${extension}`;
}

export function formatTimestamp(input: string): string {
  // Check if input is in ISO format (e.g., "2024-06-21T09:31:39Z")
  if (input.includes('T') && input.includes('-')) {
    try {
      const date = new Date(input)
      if (isNaN(date.getTime())) {
        throw new Error('Invalid ISO date')
      }
      
      // Format as DD.MM.YYYY HH:MM:SS in Berlin timezone
      return date.toLocaleString('de-DE', { 
        timeZone: 'Europe/Berlin',
        day: '2-digit',
        month: '2-digit', 
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      })
    } catch (e) {
      console.warn('Failed to parse ISO date:', input, e)
      return 'Invalid Date'
    }
  }
  
  // Check if input is in old format (DDMMYY-HHMMSS)
  const oldFormatRegex = /^\d{6}-\d{6}$/
  if (oldFormatRegex.test(input)) {
    // Extract date and time parts
    const datePart = input.slice(0, 6)
    const timePart = input.slice(7, 13)

    // Format date
    const day = datePart.slice(0, 2)
    const month = datePart.slice(2, 4)
    const year = '20' + datePart.slice(4, 6) // Assume 20xx for 2-digit years

    // Format time
    const hours = timePart.slice(0, 2)
    const minutes = timePart.slice(2, 4)
    const seconds = timePart.slice(4, 6)

    // Construct and return the formatted timestamp (DD.MM.YYYY HH:MM:SS)
    return `${day}.${month}.${year} ${hours}:${minutes}:${seconds}`
  }
  
  // If neither format matches, return the input as-is or a fallback
  console.warn('Unknown date format:', input)
  return input || 'Unknown Date'
}

export function formatLocation(coords: ComponentLocation): string {
  const { lat, lon } = coords;
  return `${lat.toFixed(6)}, ${lon.toFixed(6)}`;
}

export function formatLocationMapsLink(coords: ComponentLocation): string {
  const { lat, lon } = coords;
  return `https://www.google.com/maps/place/${lat.toFixed(6)},${lon.toFixed(6)}`;
}

export function componentBounds(component_bbx: ComponentBoundingBox): Array<number> {
  // Add defensive programming for unexpected data structures
  if (!component_bbx || !Array.isArray(component_bbx) || component_bbx.length < 3) {
    console.warn('Invalid bounding box data:', component_bbx)
    return [0, 0, 0] // Return safe defaults
  }
  
  // component_bbx is [X, Y, Z] - dimensions of the component
  const bnds_x = component_bbx[0] // X dimension
  const bnds_y = component_bbx[1] // Y dimension
  const bnds_z = component_bbx[2] // Z dimension
  
  // Ensure all values are numbers
  if (typeof bnds_x !== 'number' || typeof bnds_y !== 'number' || typeof bnds_z !== 'number') {
    console.warn('Non-numeric bounding box values:', { bnds_x, bnds_y, bnds_z })
    return [0, 0, 0] // Return safe defaults
  }
  
  return [bnds_x, bnds_y, bnds_z]
}

// Resolve a static asset URL: use NEXT_STATIC_BASE_URL in production, fallback to Next public path locally
export function resolveStatic(path: string): string {
  const base = process.env.NEXT_STATIC_BASE_URL || ''
  // In SSR, window is undefined; assume production if base is set
  const isLocal = typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
  if (isLocal || !base) return path
  const normalizedBase = base.endsWith('/') ? base : base + '/'
  const cleanedPath = path.startsWith('/') ? path.slice(1) : path
  return normalizedBase + cleanedPath
}

export function generateGrasshopperPanelXML(componentId: string): string {
  return `<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<Archive name="Root">
  <!--Grasshopper archive-->
  <!--Grasshopper and GH_IO.dll are copyrighted by Robert McNeel & Associates-->
  <!--Archive generated by GH_IO.dll file utility library {0.2.0002}-->
  <items count="1">
    <item name="ArchiveVersion" type_name="gh_version" type_code="80">
      <Major>0</Major>
      <Minor>2</Minor>
      <Revision>2</Revision>
    </item>
  </items>
  <chunks count="1">
    <chunk name="Clipboard">
      <items count="1">
        <item name="plugin_version" type_name="gh_version" type_code="80">
          <Major>1</Major>
          <Minor>0</Minor>
          <Revision>8</Revision>
        </item>
      </items>
      <chunks count="6">
        <chunk name="DocumentHeader">
          <items count="5">
            <item name="DocumentID" type_name="gh_guid" type_code="9">88c1ad12-5863-4eda-aed9-711bb46a5fdd</item>
            <item name="Preview" type_name="gh_string" type_code="10">Shaded</item>
            <item name="PreviewMeshType" type_name="gh_int32" type_code="3">1</item>
            <item name="PreviewNormal" type_name="gh_drawing_color" type_code="36">
              <ARGB>100;150;0;0</ARGB>
            </item>
            <item name="PreviewSelected" type_name="gh_drawing_color" type_code="36">
              <ARGB>100;0;150;0</ARGB>
            </item>
          </items>
        </chunk>
        <chunk name="DefinitionProperties">
          <items count="4">
            <item name="Date" type_name="gh_date" type_code="8">638477728978375110</item>
            <item name="Description" type_name="gh_string" type_code="10"></item>
            <item name="KeepOpen" type_name="gh_bool" type_code="1">false</item>
            <item name="Name" type_name="gh_string" type_code="10">250902_DDU_CSC_GrasshopperInterface.gh</item>
          </items>
          <chunks count="3">
            <chunk name="Revisions">
              <items count="1">
                <item name="RevisionCount" type_name="gh_int32" type_code="3">0</item>
              </items>
            </chunk>
            <chunk name="Projection">
              <items count="2">
                <item name="Target" type_name="gh_drawing_point" type_code="30">
                  <X>2</X>
                  <Y>-12</Y>
                </item>
                <item name="Zoom" type_name="gh_single" type_code="5">2.2537477</item>
              </items>
            </chunk>
            <chunk name="Views">
              <items count="1">
                <item name="ViewCount" type_name="gh_int32" type_code="3">0</item>
              </items>
            </chunk>
          </chunks>
        </chunk>
        <chunk name="RcpLayout">
          <items count="1">
            <item name="GroupCount" type_name="gh_int32" type_code="3">0</item>
          </items>
        </chunk>
        <chunk name="ValueTable">
          <items count="2">
            <item name="K3DSettings.UnitLength" type_name="gh_string" type_code="10">auto</item>
            <item name="K3DSettings.UnitsSystem" type_name="gh_string" type_code="10">SI</item>
          </items>
        </chunk>
        <chunk name="GHALibraries">
          <items count="1">
            <item name="Count" type_name="gh_int32" type_code="3">1</item>
          </items>
          <chunks count="1">
            <chunk name="Library" index="0">
              <items count="4">
                <item name="Author" type_name="gh_string" type_code="10">Robert McNeel &amp; Associates</item>
                <item name="Id" type_name="gh_guid" type_code="9">00000000-0000-0000-0000-000000000000</item>
                <item name="Name" type_name="gh_string" type_code="10">Grasshopper</item>
                <item name="Version" type_name="gh_string" type_code="10">8.22.25217.12451</item>
              </items>
            </chunk>
          </chunks>
        </chunk>
        <chunk name="DefinitionObjects">
          <items count="1">
            <item name="ObjectCount" type_name="gh_int32" type_code="3">1</item>
          </items>
          <chunks count="1">
            <chunk name="Object" index="0">
              <items count="2">
                <item name="GUID" type_name="gh_guid" type_code="9">59e0b89a-e487-49f8-bab8-b5bab16be14c</item>
                <item name="Name" type_name="gh_string" type_code="10">Panel</item>
              </items>
              <chunks count="1">
                <chunk name="Container">
                  <items count="8">
                    <item name="Description" type_name="gh_string" type_code="10">A panel for custom notes and text values</item>
                    <item name="InstanceGuid" type_name="gh_guid" type_code="9">ecb48a8a-add9-485e-9337-f4f48cb8944a</item>
                    <item name="Name" type_name="gh_string" type_code="10">Panel</item>
                    <item name="NickName" type_name="gh_string" type_code="10">ComponentID</item>
                    <item name="Optional" type_name="gh_bool" type_code="1">false</item>
                    <item name="ScrollRatio" type_name="gh_double" type_code="6">0</item>
                    <item name="SourceCount" type_name="gh_int32" type_code="3">0</item>
                    <item name="UserText" type_name="gh_string" type_code="10">${componentId}</item>
                  </items>
                  <chunks count="2">
                    <chunk name="Attributes">
                      <items count="6">
                        <item name="Bounds" type_name="gh_drawing_rectanglef" type_code="35">
                          <X>57</X>
                          <Y>56</Y>
                          <W>291</W>
                          <H>53</H>
                        </item>
                        <item name="MarginLeft" type_name="gh_int32" type_code="3">0</item>
                        <item name="MarginRight" type_name="gh_int32" type_code="3">0</item>
                        <item name="MarginTop" type_name="gh_int32" type_code="3">0</item>
                        <item name="Pivot" type_name="gh_drawing_pointf" type_code="31">
                          <X>57.319855</X>
                          <Y>56.72162</Y>
                        </item>
                        <item name="Selected" type_name="gh_bool" type_code="1">true</item>
                      </items>
                    </chunk>
                    <chunk name="PanelProperties">
                      <items count="7">
                        <item name="Colour" type_name="gh_drawing_color" type_code="36">
                          <ARGB>255;255;255;255</ARGB>
                        </item>
                        <item name="DrawIndices" type_name="gh_bool" type_code="1">true</item>
                        <item name="DrawPaths" type_name="gh_bool" type_code="1">true</item>
                        <item name="Multiline" type_name="gh_bool" type_code="1">true</item>
                        <item name="SpecialCodes" type_name="gh_bool" type_code="1">false</item>
                        <item name="Stream" type_name="gh_bool" type_code="1">false</item>
                        <item name="Wrap" type_name="gh_bool" type_code="1">true</item>
                      </items>
                    </chunk>
                  </chunks>
                </chunk>
              </chunks>
            </chunk>
          </chunks>
        </chunk>
      </chunks>
    </chunk>
  </chunks>
</Archive>`
}