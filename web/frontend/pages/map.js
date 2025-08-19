import { Map, Raster, Line } from '@carbonplan/maps'
import { Colorbar, useColormap } from '@carbonplan/colormaps'
import { useState, useEffect, useCallback } from 'react'
import dynamic from 'next/dynamic'
import Papa from 'papaparse'

// Dynamically import Plot component with no SSR to avoid self is not defined error
const Plot = dynamic(() => import('react-plotly.js'), { 
  ssr: false,
  loading: () => <div>Loading plot...</div>
});

const yearOptions = [2005,2006,2007,2008,2009,2010,2011,2012,2013,2014,2015,2016,2017,2018,2019,2020,2021,2022,2023,2024]
const variableOptions = [
  { value: 'tas', label: 'Temperature (°C)' },
  { value: 'pr', label: 'Precipitation (kg/(m2*s))' },
  { value: 'clt', label: 'Cloud Area Fraction (%)' },
  { value: 'od550aer', label: 'Aerosol Optical Depth at 550nm' },
  { value: 'tos', label: 'Sea Surface Temperature (°C)' },
]
const errorVariableOptions = [
  { value: 'tas_error', label: 'Temperature (°C)' },
  { value: 'pr_error', label: 'Precipitation (kg/(m2*s))' },
  { value: 'clt_error', label: 'Cloud Area Fraction (%)' },
  { value: 'od550aer_error', label: 'Aerosol Optical Depth at 550nm' },
  { value: 'tos_error', label: 'Sea Surface Temperature (°C)' },
]

const modelOptions = [
  { value: 'CanESM5', label: 'CanESM5' },
  { value: 'IPSL-CM6A-LR', label: 'IPSL-CM6A-LR' },
  { value: 'MPI-ESM1-2-LR', label: 'MPI-ESM1-2-LR' },
  { value: 'CESM2-WACCM', label: 'CESM2-WACCM' },
  { value: 'KACE-1-0-G', label: 'KACE-1-0-G' },
]

// Time series region options
const regionOptions = [
  { value: 'global', label: 'Global' },
  { value: 'tropics', label: 'Tropics' },
  { value: 'northern_hemisphere', label: 'Northern Hemisphere' },
  { value: 'southern_hemisphere', label: 'Southern Hemisphere' },
]

// Time series variable options (without error versions)
const timeseriesVariableOptions = [
  { value: 'tas', label: 'Temperature (°C)' },
  { value: 'pr', label: 'Precipitation (kg/(m2*s))' },
  { value: 'clt', label: 'Cloud Area Fraction (%)' },
  { value: 'od550aer', label: 'Aerosol Optical Depth at 550nm' },
  { value: 'tos', label: 'Sea Surface Temperature (°C)' },
]

// Define clim ranges for each variable
const climOptions = {
  tas: [-25, 35],
  pr: [0, 0.00000001],
  clt: [0, 100],
  od550aer: [0, 1],
  tos: [-2, 32],
  tas_error: [-10, 10],
  pr_error: [-0.000000005, 0.000000005],
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

const MapPage = () => {
  const [selectedYear, setSelectedYear] = useState(yearOptions[0])
  const [showError, setShowError] = useState(false)
  const [selectedVariable, setSelectedVariable] = useState(variableOptions[2].value)
  const [selectedModel, setSelectedModel] = useState(modelOptions[0].value)

  // Time series state
  const [timeseriesVariable, setTimeseriesVariable] = useState('tas')
  const [timeseriesRegion, setTimeseriesRegion] = useState('global')
  const [timeseriesData, setTimeseriesData] = useState(null)
  const [timeseriesLoading, setTimeseriesLoading] = useState(false)
  const [timeseriesError, setTimeseriesError] = useState(null)
  const [timeseriesTransitioning, setTimeseriesTransitioning] = useState(false)
  const [isClient, setIsClient] = useState(false)

  // Ensure we're on the client side
  useEffect(() => {
    setIsClient(true);
  }, []);

  // Debounced time series data fetching
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      fetchTimeseriesData();
    }, 300);
    
    return () => clearTimeout(timeoutId);
  }, [timeseriesVariable, timeseriesRegion]);

  const fetchTimeseriesData = async () => {
    if (!timeseriesTransitioning) {
      setTimeseriesLoading(true);
    }
    setTimeseriesError(null);
    
    try {
      // Load both model and observation CSV files directly
      const [modelResponse, obsResponse] = await Promise.all([
        fetch('/model_zonal_mean.csv'),
        fetch('/observation_zonal_mean.csv')
      ]);

      if (!modelResponse.ok || !obsResponse.ok) {
        throw new Error('Failed to load zonal mean CSV files');
      }

      const [modelCsvText, obsCsvText] = await Promise.all([
        modelResponse.text(),
        obsResponse.text()
      ]);

      // Parse both CSV files
      const modelParseResult = Papa.parse(modelCsvText, {
        header: true,
        skipEmptyLines: true,
        transformHeader: (header) => header.trim()
      });

      const obsParseResult = Papa.parse(obsCsvText, {
        header: true,
        skipEmptyLines: true,
        transformHeader: (header) => header.trim()
      });

      if (modelParseResult.errors.length > 0 || obsParseResult.errors.length > 0) {
        throw new Error('CSV parsing error');
      }

      const modelData = modelParseResult.data;
      const obsData = obsParseResult.data;

      // Filter model data for selected variable and region
      const filteredModelData = modelData.filter(row => 
        row.region === timeseriesRegion && 
        row[timeseriesVariable] && 
        !isNaN(parseFloat(row[timeseriesVariable]))
      ).map(row => ({
        time: row.time,
        model: row.model,
        value: parseFloat(row[timeseriesVariable])
      }));

      // Filter observation data for selected variable and region
      const filteredObsData = obsData.filter(row => 
        row.region === timeseriesRegion && 
        row[timeseriesVariable] && 
        !isNaN(parseFloat(row[timeseriesVariable]))
      ).map(row => ({
        time: row.time,
        value: parseFloat(row[timeseriesVariable])
      }));

      // Transform data to match expected structure
      setTimeseriesData({
        model_data: filteredModelData,
        observation_data: filteredObsData
      });
    } catch (err) {
      console.error('Error fetching time series data:', err);
      setTimeseriesError(err.message);
    } finally {
      setTimeseriesLoading(false);
      setTimeseriesTransitioning(false);
    }
  };

  const createTimeseriesPlotData = () => {
    if (!timeseriesData) return [];

    const traces = [];
    
    // Get observation time range to determine overlap
    const obsData = timeseriesData.observation_data || [];
    if (obsData.length === 0) return traces;
    
    const obsTimestamps = obsData.map(d => new Date(d.time).getTime());
    const minObsTime = Math.min(...obsTimestamps);
    const maxObsTime = Math.max(...obsTimestamps);
    
    // Group model data by model name and filter to overlap period
    const modelGroups = {};
    timeseriesData.model_data.forEach(point => {
      const pointTime = new Date(point.time).getTime();
      // Only include model data that falls within observation time range
      if (pointTime >= minObsTime && pointTime <= maxObsTime) {
        if (!modelGroups[point.model]) {
          modelGroups[point.model] = [];
        }
        modelGroups[point.model].push(point);
      }
    });

    // Add each model as grey lines (only overlap period)
    Object.entries(modelGroups).forEach(([modelName, modelData]) => {
      // Sort by time
      const sortedData = modelData.sort((a, b) => new Date(a.time) - new Date(b.time));
      
      traces.push({
        x: sortedData.map(d => d.time),
        y: sortedData.map(d => d.value),
        type: 'scatter',
        mode: 'lines',
        name: modelName,
        line: { 
          color: '#888888',  // Grey color
          width: 0.5
        },
        opacity: 0.7,  // Very low opacity for cloudy effect
        hovertemplate: `${modelName}<br>%{x}<br>%{y:.2f}<extra></extra>`
      });
    });

    // Add observation data in Google blue (full range within model overlap)
    const sortedObs = obsData
      .filter(d => {
        const obsTime = new Date(d.time).getTime();
        return obsTime >= minObsTime && obsTime <= maxObsTime;
      })
      .sort((a, b) => new Date(a.time) - new Date(b.time));
    
    if (sortedObs.length > 0) {
      traces.push({
        x: sortedObs.map(d => d.time),
        y: sortedObs.map(d => d.value),
        type: 'scatter',
        mode: 'lines',
        name: 'Observations',
        line: { 
          color: '#4285F4',  // Google blue
          width: 3
        },
        hovertemplate: 'Observations<br>%{x}<br>%{y:.2f}<extra></extra>'
      });
    }

    return traces;
  };

  const getVariableLabel = (variable) => {
    const option = timeseriesVariableOptions.find(v => v.value === variable);
    return option ? option.label : variable;
  };

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
    <div className="main-content map-page">
      {/* Time Series Section */}
      <section className="section">
        <h2>Zonal Mean Time Series</h2>
        <p className="map-description">
          Compare climate model projections (grey lines) with observational data (blue line) over time.
        </p>
        <div style={{ marginBottom: '15px', display: 'flex', gap: '20px', alignItems: 'center', flexWrap: 'wrap' }}>
          <div>
            <label style={{ fontSize: '0.9rem' }}>
              Variable:&nbsp;
              <select
                value={timeseriesVariable}
                onChange={(e) => {
                  setTimeseriesTransitioning(true);
                  setTimeseriesVariable(e.target.value);
                }}
                className="widget-select"
              >
                {timeseriesVariableOptions.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </label>
          </div>
          <div>
            <label style={{ fontSize: '0.9rem' }}>
              Region:&nbsp;
              <select
                value={timeseriesRegion}
                onChange={(e) => {
                  setTimeseriesTransitioning(true);
                  setTimeseriesRegion(e.target.value);
                }}
                className="widget-select"
              >
                {regionOptions.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </label>
          </div>
        </div>
        {/* Loading/Error/Plot with smooth transitions */}
        <div style={{ position: 'relative', minHeight: '500px' }}>
          {/* Loading overlay */}
          {(timeseriesLoading || timeseriesTransitioning) && (
            <div style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: 'rgba(255, 255, 255, 0.8)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 10,
              transition: 'opacity 0.3s ease'
            }}>
              <div className="loading">Loading time series...</div>
            </div>
          )}
          
          {/* Error overlay */}
          {timeseriesError && (
            <div style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: 'rgba(255, 255, 255, 0.95)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 10
            }}>
              <div className="error">Error: {timeseriesError}</div>
            </div>
          )}
          
          {/* Chart with opacity transition */}
          <div style={{ 
            opacity: (timeseriesLoading || timeseriesTransitioning || timeseriesError) ? 0.3 : 1,
            transition: 'opacity 0.3s ease',
            minHeight: '500px'
          }}>
            {isClient && timeseriesData && (
              <Plot
                data={createTimeseriesPlotData()}
                layout={{
                    title: `Zonal Mean ${getVariableLabel(timeseriesVariable)} for ${timeseriesRegion.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}`,
                    xaxis: { title: 'Time' },
                    yaxis: { title: `${getVariableLabel(timeseriesVariable)}` },
                    legend: {
                      orientation: 'h',
                      x: 0,
                      y: -0.2,
                      xanchor: 'left',
                      yanchor: 'top',
                      bgcolor: 'rgba(255,255,255,0.8)',
                      bordercolor: '#e5e7eb',
                      borderwidth: 1,
                      font: { size: 11 }
                    },
                    margin: { t: 40, b: 80 }
                  }}
                config={{
                    responsive: true,
                    displayModeBar: true,
                    displaylogo: false,
                    modeBarButtonsToRemove: ['pan2d', 'lasso2d', 'select2d']
                  }}
                style={{ width: '100%', height: '500px' }}
                useResizeHandler={true}
              />
            )}
          </div>
        </div>
      </section>

      {/* Map Section */}
      <section className="section">
        <div className="map-title">Climate Map</div>
        <div className="map-container">
          <Map zoom={1} center={[0, 0]} debug={false}>
            <Line
              color={'white'}
              source={'https://storage.googleapis.com/carbonplan-maps/basemaps/land'}
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
            
            {/* Map overlays and controls */}
            <div className="map-overlay">
              <div className="control-group">
                <label className="control-label">Year</label>
                <input
                  type="range"
                  min={0}
                  max={yearOptions.length - 1}
                  value={yearOptions.indexOf(selectedYear)}
                  onChange={e => setSelectedYear(yearOptions[parseInt(e.target.value)])}
                  className="time-slider"
                />
                <div className="time-display">{selectedYear}</div>
              </div>
              <div className="control-group">
                <label className="control-label">Variable</label>
                <select
                  value={selectedVariable}
                  onChange={handleVariableChange}
                  className="widget-select"
                >
                  {currentVariableOptions.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
                <label style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: 8 }}>
                  <input
                    type="checkbox"
                    checked={showError}
                    onChange={handleToggle}
                  />
                  Show error
                </label>
              </div>
              <div className="control-group">
                <label className="control-label">Model</label>
                <select
                  value={selectedModel}
                  onChange={e => setSelectedModel(e.target.value)}
                  className="widget-select"
                >
                  {modelOptions.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
            </div>
            {/* Colorbar in lower left */}
            <div style={{ position: 'absolute', bottom: 20, left: 16, zIndex: 10 }}>
              <Colorbar colormap={colormap} clim={clim} label={variableLabel} horizontal={true} style={{ width: 200 }} />
            </div>
          </Map>
        </div>
      </section>
    </div>
  );
};

export default MapPage;