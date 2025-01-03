'use client'

export default function ComponentDetailMap({
  lat,
  lon
} : {
  lat: Number,
  lon: Number
}) {

  // Lat/Lon
  const mapSrc = `https://maps.google.com/maps?q=${lat},${lon}&z=15&output=embed`

  return (
    <div className='w-full md:w-[300px] md:h-[200px]'>
      <iframe
        width="100%"
        height="200"
        style={{ border: 0 }}
        src={mapSrc}
        allowFullScreen
        aria-hidden="false"
        tabIndex={0}
        className='rounded-md overflow-hidden'
      ></iframe>
    </div>
  )
}
