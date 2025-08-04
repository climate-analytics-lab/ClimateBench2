import React, { useState, useEffect, useCallback, useMemo } from 'react';
import dynamic from 'next/dynamic';
import Papa from 'papaparse';

// Dynamically import Plot with SSR disabled to prevent "self is not defined" error
const Plot = dynamic(() => import('react-plotly.js'), { 
  ssr: false,
  loading: () => <div className="loading">Loading chart...</div>
});



const ProbabilisticScores = () => {
  const [widgets, setWidgets] = useState({
    variable: 'tas',
    region: 'global',
    metric: 'MAE'
  });

  const [plotData, setPlotData] = useState([]);
  const [plotLayout, setPlotLayout] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [isTransitioning, setIsTransitioning] = useState(false);

  // Debounced handler to prevent rapid changes
  const handleWidgetChange = useCallback((widgetName, value) => {
    setIsTransitioning(true);
    setWidgets(prev => ({
      ...prev,
      [widgetName]: value
    }));
  }, []);

  // Debounced effect to prevent rapid API calls
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      fetchTimeSeriesData();
    }, 300); // 300ms delay

    return () => clearTimeout(timeoutId);
  }, [widgets.variable, widgets.region, widgets.metric]);

  const fetchTimeSeriesData = async () => {
    if (!isTransitioning) {
      setLoading(true);
    }
    setError('');
    try {
      // Choose the appropriate CSV file based on metric
      const csvFile = widgets.metric === 'CRPS' 
        ? '/crps_benchmark_results.csv' 
        : '/benchmark_results_time_series.csv';
      
      // Load CSV file directly from frontend public directory
      const response = await fetch(csvFile);
      if (!response.ok) throw new Error('Failed to load CSV file');
      const csvText = await response.text();
      
      // Parse CSV using Papa Parse
      const parseResult = Papa.parse(csvText, {
        header: true,
        skipEmptyLines: true,
        transformHeader: (header) => header.trim()
      });
      
      if (parseResult.errors.length > 0) {
        throw new Error('CSV parsing error: ' + parseResult.errors[0].message);
      }
      
      const csvData = parseResult.data;
      
              // Filter data based on selected variable and metric
        const filteredData = widgets.metric === 'CRPS'
          ? csvData.filter(row => 
              row.variable === widgets.variable && 
              row.metric === 'CRPS'
            )
          : csvData.filter(row => 
              row.variable === widgets.variable && 
              row.metric === widgets.metric
            );

      // Group data by model
      const modelGroups = {};
      filteredData.forEach(row => {
        const model = row.model;
        const regionValue = row[widgets.region]; // Get value for selected region
        
        if (!modelGroups[model]) {
          modelGroups[model] = [];
        }
        
        if (regionValue && !isNaN(parseFloat(regionValue))) {
          modelGroups[model].push({
            timestamp: row.time,
            value: parseFloat(regionValue)
          });
        }
      });

      // Create a trace for each model
      const traces = Object.entries(modelGroups).map(([model, modelData], index) => {
        // Sort by timestamp
        const sortedData = modelData.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
        
        // Define Google blue color variations for different models
        const colors = [
          '#4285F4', '#1a73e8', '#1967d2', '#1557b0', '#174ea6',
          '#5094ed', '#6ba6f7', '#8ab4f8', '#aecbfa', '#c8d7fc',
          '#2d5aa0', '#1c4587'
        ];
        
        return {
          x: sortedData.map(d => d.timestamp),
          y: sortedData.map(d => d.value),
          type: 'scatter',
          mode: 'lines',
          name: model,
          line: { 
            color: colors[index % colors.length],
            width: 2
          }
        };
      });

      setPlotData(traces);

      setPlotLayout({
        title: `${widgets.metric} Time Series for ${widgets.variable} (${widgets.region})`,
        xaxis: { title: 'Time' },
        yaxis: { title: `${widgets.metric} for ${widgets.variable}` },
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
      });
    } catch (err) {
      setError(err.message);
      setPlotData([]);
    } finally {
      setLoading(false);
      setIsTransitioning(false);
    }
  };



  return (
    <div className="main-content probabilistic-scores">
      <h2 className="section-title">Probabilistic Scores</h2>
      <p>This page shows climate model evaluation metrics comparing predictions with observations. You can select between MAE (Mean Absolute Error), RMSE (Root Mean Square Error), and CRPS (Continuous Ranked Probability Score) to analyze model performance across different variables and regions over time. CRPS data is loaded from dedicated benchmark results.</p>
      
      <div className="widget-menu">
        <div className="widget-row">
          <div className="widget-group">
            <label htmlFor="variable-select">Variable</label>
            <select 
              id="variable-select" 
              className="widget-select"
              value={widgets.variable}
              onChange={(e) => handleWidgetChange('variable', e.target.value)}
            >
              <option value="tas">Air Temperature (tas)</option>
              <option value="pr">Precipitation (pr)</option>
              <option value="tos">Sea Surface Temperature (tos)</option>
              <option value="clt">Cloud Cover (clt)</option>
              <option value="od550aer">Aerosol Optical Depth (od550aer)</option>
            </select>
          </div>
          
          <div className="widget-group">
            <label htmlFor="region-select">Region</label>
            <select 
              id="region-select" 
              className="widget-select"
              value={widgets.region}
              onChange={(e) => handleWidgetChange('region', e.target.value)}
            >
              <option value="global">Global</option>
              <option value="tropics">Tropics</option>
              <option value="northern_hemisphere">Northern Hemisphere</option>
              <option value="southern_hemisphere">Southern Hemisphere</option>
            </select>
          </div>
          
          <div className="widget-group">
            <label htmlFor="metric-select">Metric</label>
            <select 
              id="metric-select" 
              className="widget-select"
              value={widgets.metric}
              onChange={(e) => handleWidgetChange('metric', e.target.value)}
            >
              <option value="MAE">Mean Absolute Error (MAE)</option>
              <option value="RMSE">Root Mean Square Error (RMSE)</option>
              <option value="CRPS">Continuous Ranked Probability Score (CRPS)</option>
            </select>
          </div>
        </div>
      </div>

      {/* Chart Section */}
      <div className="chart-section" style={{ position: 'relative', minHeight: '500px' }}>
        {/* Loading overlay */}
        {(loading || isTransitioning) && (
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
            <div className="loading">Loading data...</div>
          </div>
        )}
        
        {/* Error overlay */}
        {error && (
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
            <div className="error">Error: {error}</div>
          </div>
        )}
        
        {/* Chart placeholder to maintain layout */}
        <div style={{ 
          width: '100%', 
          height: '500px',
          opacity: (loading || isTransitioning || error) ? 0.3 : 1,
          transition: 'opacity 0.3s ease'
        }}>
          {plotData.length > 0 ? (
            <Plot
              data={plotData}
              layout={plotLayout}
              config={{
                responsive: true,
                displayModeBar: true,
                modeBarButtonsToRemove: ['pan2d', 'lasso2d']
              }}
              style={{ width: '100%', height: '500px' }}
            />
          ) : !loading && !error && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              color: '#666'
            }}>
              No data available for the selected variable.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ProbabilisticScores;
