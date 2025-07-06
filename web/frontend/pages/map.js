import { Map, Raster, Line } from '@carbonplan/maps'
import { useColormap } from '@carbonplan/colormaps'
import { useState } from 'react'

export default function MapPage() {
  const [colormapName, setColormapName] = useState('warm')
  const [opacity, setOpacity] = useState(1)
  const [timeIndex, setTimeIndex] = useState(0)
  
  const colormap = useColormap(colormapName)
  
  // Generate time steps (you can adjust this based on your data)
  const timeSteps = Array.from({ length: 12 }, (_, i) => {
    const date = new Date(2020, i, 1)
    return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
  })

  return (
    <div className="main-content map-page">
      <h2 className="section-title">Climate Map</h2>
      <div className="map-container">
        <Map zoom={2} center={[0, 0]} debug={false}>
          <Line
            color={'white'}
            source={
              'https://storage.googleapis.com/carbonplan-maps/basemaps/land'
            }
            variable={'land'}
          />
          <Raster
            colormap={colormap}
            clim={[100, 300]}
            display={true}
            opacity={opacity}
            mode={'texture'}
            source={
              "http://localhost:8000/public/data/regridded.zarr/"
            }
            variable={'tas'}
          />
        </Map>
      </div>
      
      <div className="map-overlay">
        <h3 className="map-title">Climate Data Visualization</h3>
        <p className="map-description">
          Interactive map showing temperature data from climate models. 
          Use the controls to adjust the visualization.
        </p>
      </div>
      
      <div className="map-controls">
        <div className="control-group">
          <label className="control-label">Colormap</label>
          <select 
            className="control-select"
            value={colormapName}
            onChange={(e) => setColormapName(e.target.value)}
          >
            <option value="warm">Warm</option>
            <option value="cool">Cool</option>
            <option value="fire">Fire</option>
            <option value="earth">Earth</option>
            <option value="water">Water</option>
            <option value="heart">Heart</option>
            <option value="wind">Wind</option>
            <option value="rainbow">Rainbow</option>
            <option value="sinebow">Sinebow</option>
            <option value="reds">Reds</option>
            <option value="blues">Blues</option>
            <option value="greens">Greens</option>
            <option value="purples">Purples</option>
            <option value="greys">Greys</option>
          </select>
        </div>
        
        <div className="control-group">
          <label className="control-label">Opacity</label>
          <select 
            className="control-select"
            value={opacity}
            onChange={(e) => setOpacity(parseFloat(e.target.value))}
          >
            <option value={0.3}>30%</option>
            <option value={0.5}>50%</option>
            <option value={0.7}>70%</option>
            <option value={1}>100%</option>
          </select>
        </div>
        
        <div className="control-group">
          <label className="control-label">Time Period</label>
          <div className="time-slider-container">
            <input
              type="range"
              min="0"
              max={timeSteps.length - 1}
              value={timeIndex}
              onChange={(e) => setTimeIndex(parseInt(e.target.value))}
              className="time-slider"
            />
            <div className="time-display">
              {timeSteps[timeIndex]}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
} 