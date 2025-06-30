import { Map, Raster, Line } from '@carbonplan/maps'
import { useColormap } from '@carbonplan/colormaps'

const Index = () => {
  const colormap = useColormap('warm')

  return (
    <div style={{ position: 'absolute', top: 0, bottom: 0, width: '100%' }}>
      <Map zoom={2} center={[0, 0]} debug={false}>
        <Line
          color={'white'}
          source={
            'https://storage.googleapis.com/carbonplan-maps/basemaps/land'
          }
          variable={'land'}
        />
        {/* <Raster
          source= "http://localhost:8000/public/data/regridded.zarr/"
          variable="tas"
          dimensions={['y', 'x']}
          clim={[100, 300]} // adjust if needed
          mode="texture"
          display={true}
          colormap={useColormap('warm')}
        /> */}
        <Raster
          colormap={colormap}
          clim={[100, 300]}
          display={true}
          opacity={1}
          mode={'texture'}
          source={
            "http://localhost:8000/public/data/regridded.zarr/"
          }
          variable={'tas'}
        />
      </Map>
    </div>
  )
}

export default Index
