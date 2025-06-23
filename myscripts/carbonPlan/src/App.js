import React from 'react'
import { Map, Raster } from '@carbonplan/maps'
import { useColormap } from '@carbonplan/colormaps'

const PrecipitationMap = () => {
  const colormap = useColormap('rainbow', { count: 7, mode: 'light', format: 'hex' })

  return (
    <Map>
      <Raster
        colormap={colormap}
        clim={[0, 20]}
        source="https://storage.googleapis.com/cmip6/CMIP6/ScenarioMIP/IPSL/IPSL-CM6A-LR/ssp245/r1i1p1f1/Amon/pr/gr/v20190119"
        variable="pr"
        dimensions={['lat', 'lon']}
      />
    </Map>
  )
}

export default PrecipitationMap
