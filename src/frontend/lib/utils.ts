import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

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