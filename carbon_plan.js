import { Map, Raster } from '@carbonplan/maps'
import { useColormap } from '@carbonplan/colormaps'

const TemperatureMap = () => {
  const colormap = useColormap('warm')

  return (
    <Map>
      <Raster
        colormap={colormap}
        clim={[-20, 30]}
        source={
          'https://storage.googleapis.com/carbonplan-scratch/map-tests/processed/temp'
        }
        variable={'temperature'}
        dimensions={['y', 'x']}
      />
    </Map>
  )
} 