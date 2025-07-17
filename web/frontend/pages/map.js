import { Map, Raster, Line } from '@carbonplan/maps'
import { Colorbar, useColormap } from '@carbonplan/colormaps'
import { useState } from 'react'

const yearOptions = [2005,2006,2007,2008,2009,2010,2011,2012,2013,2014,2015,2016,2017,2018,2019,2020,2021,2022,2023,2024]
const variableOptions = [
  { value: 'tas', label: 'Temperature (K)' },
  { value: 'pr', label: 'Precipitation (kg/(m2*s)' },
  { value: 'clt', label: 'Cloud Area Fraction (%)' },
  { value: 'od550aer', label: 'Aerosol Optical Depth at 550nm' },
  { value: 'tos', label: 'Sea Surface Temperature (C)' },
]
const errorVariableOptions = [
  { value: 'tas_error', label: 'Temperature (K)' },
  { value: 'pr_error', label: 'Precipitation (kg/(m2*s)' },
  { value: 'clt_error', label: 'Cloud Area Fraction (%)' },
  { value: 'od550aer_error', label: 'Aerosol Optical Depth at 550nm' },
  { value: 'tos_error', label: 'Sea Surface Temperature (C)' },
]

const modelOptions = [
  // { value: 'FGOALS-g3', label: 'FGOALS-g3' },
  // { value: 'FGOALS-f3-L', label: 'FGOALS-f3-L' },
  { value: 'CanESM5', label: 'CanESM5' },
  // { value: 'ACCESS-CM2', label: 'ACCESS-CM2' },
  // { value: 'EC-Earth3-Veg', label: 'EC-Earth3-Veg' },
  // { value: 'EC-Earth3-Veg-LR', label: 'EC-Earth3-Veg-LR' },
  // { value: 'FIO-ESM-2-0', label: 'FIO-ESM-2-0' },
  { value: 'IPSL-CM6A-LR', label: 'IPSL-CM6A-LR' },
  // { value: 'MIROC6', label: 'MIROC6' },
  { value: 'MPI-ESM1-2-LR', label: 'MPI-ESM1-2-LR' },
  // { value: 'MRI-ESM2-0', label: 'MRI-ESM2-0' },
  { value: 'CESM2-WACCM', label: 'CESM2-WACCM' },
  // { value: 'NorESM2-LM', label: 'NorESM2-LM' },
  { value: 'KACE-1-0-G', label: 'KACE-1-0-G' },
  // { value: 'GFDL-ESM4', label: 'GFDL-ESM4' },
]

// Define clim ranges for each variable
const climOptions = {
  tas: [250, 300],
  pr: [0, 0.0001],
  clt: [0, 100],
  od550aer: [0, 1],
  tos: [0, 30],
  tas_error: [-10, 10],
  pr_error: [-0.00005, 0.00005],
  clt_error: [-20, 20],
  od550aer_error: [-0.5, 0.5],
  tos_error: [-5, 5],
}

// Optionally, define a colormap for each variable
const colormapOptions = {
  tas: 'warm',
  pr: 'earth',
  clt: 'sinebow',
  od550aer: 'tealgrey',
  tos: 'pinkgreen',
  tas_error: 'orangeblue',
  pr_error: 'orangeblue',
  clt_error: 'orangeblue',
  od550aer_error: 'orangeblue',
  tos_error: 'orangeblue',
}

const Index = () => {
  const [selectedYear, setSelectedYear] = useState(yearOptions[0])
  const [showError, setShowError] = useState(false)
  const [selectedVariable, setSelectedVariable] = useState(variableOptions[2].value)
  const [selectedModel, setSelectedModel] = useState(modelOptions[0].value)

  // Choose variable list based on switch
  const currentVariableOptions = showError ? errorVariableOptions : variableOptions

  // If switching between value/error, keep the same variable type if possible
  const handleVariableChange = (e) => {
    setSelectedVariable(e.target.value)
  }

  const handleToggle = () => {
    const idx = currentVariableOptions.findIndex(v => v.value === selectedVariable)
    setShowError(!showError)
    // Try to keep the same variable type selected after toggle
    if (!showError) {
      // switching to error
      setSelectedVariable(errorVariableOptions[idx >= 0 ? idx : 0].value)
    } else {
      // switching to value
      setSelectedVariable(variableOptions[idx >= 0 ? idx : 0].value)
    }
  }

  const colormap = useColormap(colormapOptions[selectedVariable] || 'warm')
  const clim = climOptions[selectedVariable] || [0, 1]
  const variableLabel = currentVariableOptions.find(v => v.value === selectedVariable)?.label

  return (
    <div className="main-content map-page" style={{ height: '100vh', width: '100vw', position: 'relative' }}>
      <section className="section" id="zmean-time-series">
        <h2>Zonal Mean Time Series</h2>
        <p>
          Add zonal mean time series.
        </p>
      </section>

      <section className="section" id="model-map">
        <h2>Climate Map</h2>
        <div style={{ height: '80vh', width: '100%', position: 'relative' }}>
          <Map zoom={1} center={[0, 0]} debug={false}>
            <Line
              color={'white'}
              source={
                'https://storage.googleapis.com/carbonplan-maps/basemaps/land'
              }
              variable={'land'}
            />
            <Raster
              key={selectedVariable + selectedModel}
              colormap={colormap}
              clim={clim}
              display={true}
              opacity={1}
              mode={'texture'}
              source="http://localhost:8000/public/map_data_subset_pyramid.zarr/"
              variable={selectedVariable}
              selector={{ year: selectedYear, model: selectedModel }}
            />
            {/* Map controls in upper left */}
            <div
              style={{
                position: 'absolute',
                top: 16,
                left: 16,
                zIndex: 10,
                background: 'rgba(255,255,255,0.95)',
                borderRadius: 8,
                boxShadow: '0 2px 8px rgba(0,0,0,0.07)',
                padding: 16,
                minWidth: 220,
                maxWidth: 320,
              }}
            >
              <div style={{ marginBottom: 12 }}>
                <label>
                  Year:&nbsp;
                  <input
                    type="range"
                    min={0}
                    max={yearOptions.length - 1}
                    value={yearOptions.indexOf(selectedYear)}
                    onChange={e => setSelectedYear(yearOptions[parseInt(e.target.value)])}
                    style={{ verticalAlign: 'middle', width: 120 }}
                  />
                  &nbsp;<span>{selectedYear}</span>
                </label>
              </div>
              <div style={{ marginBottom: 12 }}>
                <label>
                  Variable:&nbsp;
                  <select
                    value={selectedVariable}
                    onChange={handleVariableChange}
                  >
                    {currentVariableOptions.map(opt => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </label>
                <label style={{ marginLeft: 16 }}>
                  <input
                    type="checkbox"
                    checked={showError}
                    onChange={handleToggle}
                    style={{ verticalAlign: 'middle' }}
                  />
                  &nbsp;Show error
                </label>
              </div>
              <div>
                <label>
                  Model:&nbsp;
                  <select
                    value={selectedModel}
                    onChange={e => setSelectedModel(e.target.value)}
                  >
                    {modelOptions.map(opt => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </label>
              </div>
            </div>
              {/* Colorbar in lower right */}
              <div
                style={{
                  position: 'absolute',
                  top: 490,
                  left: 16,
                  zIndex: 10,
                  background: 'white',
                  padding: 8,
                  borderRadius: 8,
                  boxShadow: '0 2px 8px rgba(0,0,0,0.07)',
                }}
              >
                <Colorbar
                  colormap={colormap}
                  clim={clim}
                  label={variableLabel}
                  units=""
                  horizontal={true}
                />
            </div>
          </Map>
        </div>
      </section>
    </div>
  )
}

export default Index