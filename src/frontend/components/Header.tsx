'use client';

import AppMenu from "./AppMenu";

export default function Header() {
  return (
    <>
      <div className="flex gap-4 p-4 border-b font-bold">
        <h1>Catalogue of Second Chances</h1>
      </div>
      <div className="md:hidden p-4">
          <AppMenu />
      </div>
    </>
  );
}