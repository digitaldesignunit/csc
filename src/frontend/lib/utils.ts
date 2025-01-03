import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"
import { ComponentBoundingBox, ComponentLocation } from "@/components/models";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function diff_mins(dt1: Date, dt2: Date) {
  // Calculate the difference in milliseconds between the two provided dates and convert it to seconds
  var diff =(dt2.getTime() - dt1.getTime()) / 1000;
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
  var zeros = new Array(len).join('0');
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
  var rnum = parseInt(hex.slice(0, 2), 16)
  var gnum = parseInt(hex.slice(2, 4), 16)
  var bnum = parseInt(hex.slice(4, 6), 16)
  if (bw) {
      // https://stackoverflow.com/a/3943023/112731
      return (rnum * 0.299 + gnum * 0.587 + bnum * 0.114) > 186
          ? '#000000'
          : '#FFFFFF';
  }
  // invert color components
  var r = (255 - rnum).toString(16);
  var g = (255 - gnum).toString(16);
  var b = (255 - bnum).toString(16);
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
  // Validate input format
  const regex = /^\d{6}-\d{6}$/
  if (!regex.test(input)) {
      throw new Error(
        "Invalid input format. Expected format is 'DDMMYY-HHMMSS'."
    )
  }

  // Extract date and time parts
  const datePart = input.slice(0, 6)
  const timePart = input.slice(7, 13)

  // Format date
  const day = datePart.slice(0, 2)
  const month = datePart.slice(2, 4)
  const year = datePart.slice(4, 6)

  // Format time
  const hours = timePart.slice(0, 2)
  const minutes = timePart.slice(2, 4)
  const seconds = timePart.slice(4, 6)

  // Construct and return the formatted timestamp
  return `${year}.${month}.${day} ${hours}:${minutes}:${seconds}`
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
  const bnds_x = component_bbx[1][0] - component_bbx[0][0]
  const bnds_y = component_bbx[1][1] - component_bbx[0][1]
  const bnds_z = component_bbx[1][2] - component_bbx[0][2]
  return [bnds_x, bnds_y, bnds_z]
}