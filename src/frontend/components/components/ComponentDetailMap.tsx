'use client'

export default function ComponentDetailMap({
  lat,
  lon
} : {
  lat: number,
  lon: number
}) {

  // Lat/Lon
  const mapSrc = `https://maps.google.com/maps?q=${lat},${lon}&z=15&output=embed`

  return (
    <div className='w-full h-[200px]'>
      <iframe
        width="100%"
        height="200"
        style={{ border: 0 }}
        src={mapSrc}
        allowFullScreen
        aria-hidden="false"
        tabIndex={0}
        className='rounded-md overflow-hidden w-full h-full'
      ></iframe>
    </div>
  )
}
