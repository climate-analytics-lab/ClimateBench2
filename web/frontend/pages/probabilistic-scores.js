import React, { useState, useEffect, useRef, useCallback } from 'react';
import dynamic from 'next/dynamic';
const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });
import { fetchProbabilisticData } from '../services/api';

const ProbabilisticScores = () => {
  const [widgets, setWidgets] = useState({
    variable: 'pr',
    metric: 'crps',
    level: 'surface',
    region: 'global',
    year: '2020',
    resolution: 'low'
  });
  
  const [chartData, setChartData] = useState([]);
  const [chartLayout, setChartLayout] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [modelNames, setModelNames] = useState([]);


  const chartContainerRef = useRef(null);

  const capitalize = (str) => {
    return str.charAt(0).toUpperCase() + str.slice(1);
  };

  const fetchAndPlotProbabilisticData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const result = await fetchProbabilisticData(
        widgets.variable,
        widgets.metric,
        widgets.level,
        widgets.region,
        widgets.year,
        widgets.resolution
      );

      if (result.error) {
        setError(result.error);
        return;
      }

      const data = result;
      const observedColor = '#4285F4'; // Google blue
      const modelColor = '#9AA0A6'; // Google grey

      const traces = [
        {
          x: data.time,
          y: data[widgets.variable],
          type: "scatter",
          mode: "lines",
          name: "Observed",
          line: { 
            width: 4, 
            color: observedColor
          },
          hovertemplate: '<b>Observed</b><br>' +
                        'Time: %{x}<br>' +
                        'Value: %{y:.3f}<br>' +
                        '<extra></extra>',
          hoverlabel: {
            bgcolor: observedColor,
            font: { color: 'white', size: 12 }
          }
        },
      ];

      if (data.predicted) {
        Object.entries(data.predicted).forEach(([modelName, predData], index) => {
          traces.push({
            x: predData.time,
            y: predData.values,
            type: "scatter",
            mode: "lines",
            name: modelName,
            line: {
              width: 2,
              color: modelColor,
              dash: 'dot',
              shape: 'spline'
            },
            opacity: 0.3,
            hovertemplate: '<b>' + modelName + '</b><br>' +
                          'Time: %{x}<br>' +
                          'Predicted: %{y:.3f}<br>' +
                          '<extra></extra>',
            hoverlabel: {
              bgcolor: modelColor,
              font: { color: 'white', size: 11 }
            }
          });
        });
      }

      setChartData(traces);
      
      // Store model names for legend
      if (data.predicted) {
        setModelNames(Object.keys(data.predicted));
      }
      
    } catch (err) {
      console.error("Failed to fetch probabilistic data:", err);
      setError('Failed to load probabilistic data');
    } finally {
      setLoading(false);
    }
  }, [widgets.variable, widgets.metric, widgets.level, widgets.region, widgets.year, widgets.resolution]);

  const updateChart = useCallback(() => {
    const variable = widgets.variable.charAt(0).toUpperCase() + widgets.variable.slice(1);
    const metric = widgets.metric.toUpperCase();
    const level = widgets.level === "surface" ? "Surface" : `${widgets.level} hPa`;
    const region = widgets.region.charAt(0).toUpperCase() + widgets.region.slice(1).replace(/_/g, " ");
    const year = widgets.year;

    setChartLayout(layout => ({
      ...layout,
      title: {
        text: `${metric} for ${variable} at ${level} - ${region} (${year})`,
        font: { size: 20, family: "Arial" },
      }
    }));
  }, [widgets.variable, widgets.metric, widgets.level, widgets.region, widgets.year]);

  const handleWidgetChange = (widgetName, value) => {
    setWidgets(prev => ({
      ...prev,
      [widgetName]: value
    }));
  };

  useEffect(() => {
    fetchAndPlotProbabilisticData();
    updateChart();
  }, [fetchAndPlotProbabilisticData, updateChart]);

  return (
    <div className="main-content probabilistic-scores">
      <h2 className="section-title">Probabilistic Scores</h2>

      <p>
        This page shows probabilistic forecast evaluation metrics for ensemble weather prediction models. 
        Probabilistic forecasts provide uncertainty estimates alongside point predictions, making them crucial 
        for decision-making in weather-sensitive applications.
      </p>

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
              <option value="tos">Sea Surface Temperature (tos)</option>
              <option value="clt">Cloud Cover (clt)</option>
              <option value="pr">Precipitation (pr)</option>
              <option value="tas">Air Temperature (tas)</option>
              <option value="areacello">Ocean Grid Cell Area (areacello)</option>
              <option value="od550aer">Aerosol Optical Depth (od550aer)</option>
              <option value="areacella">Atmospheric Grid Cell Area (areacella)</option>
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
              <option value="crps">Continuous Ranked Probability Score (CRPS)</option>
              <option value="reliability">Reliability</option>
              <option value="sharpness">Sharpness</option>
            </select>
          </div>

          <div className="widget-group">
            <label htmlFor="level-select">Level</label>
            <select 
              id="level-select" 
              className="widget-select"
              value={widgets.level}
              onChange={(e) => handleWidgetChange('level', e.target.value)}
            >
              <option value="surface">Surface</option>
              <option value="500">500 hPa</option>
              <option value="850">850 hPa</option>
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
              <option value="tropics">Tropics (20°S–20°N)</option>
              <option value="mid_latitudes">Mid-latitudes (20°–60°)</option>
              <option value="polar">Polar (60°–90°)</option>
            </select>
          </div>

          <div className="widget-group">
            <label htmlFor="year-select">Year</label>
            <select 
              id="year-select" 
              className="widget-select"
              value={widgets.year}
              onChange={(e) => handleWidgetChange('year', e.target.value)}
            >
              <option value="2020">2020</option>
              <option value="2021">2021</option>
              <option value="2022">2022</option>
              <option value="2023">2023</option>
            </select>
          </div>

          <div className="widget-group">
            <label htmlFor="resolution-select">Resolution</label>
            <select 
              id="resolution-select" 
              className="widget-select"
              value={widgets.resolution}
              onChange={(e) => handleWidgetChange('resolution', e.target.value)}
            >
              <option value="low">Low (1°)</option>
              <option value="medium">Medium (0.5°)</option>
              <option value="high">High (0.25°)</option>
            </select>
          </div>
        </div>
      </div>



      {loading && (
        <div className="loading-container">
          <div className="loading">Loading probabilistic data...</div>
        </div>
      )}

      {error && (
        <div className="error-container">
          <div className="error">Error: {error}</div>
        </div>
      )}

      {!loading && !error && (
        <div className="chart-container" ref={chartContainerRef}>
          <Plot
            data={chartData}
            layout={{
              ...chartLayout,
              width: chartContainerRef.current?.offsetWidth || 800,
              height: 500,
              margin: { l: 60, r: 60, t: 100, b: 80 },
              paper_bgcolor: 'rgba(0,0,0,0)',
              plot_bgcolor: 'rgba(0,0,0,0)',
              xaxis: { 
                title: { 
                  text: 'Time',
                  font: { size: 14, color: '#333' }
                },
                gridcolor: 'rgba(128,128,128,0.2)',
                zeroline: false,
                showline: true,
                linecolor: '#ccc',
                tickfont: { size: 12, color: '#666' }
              },
              yaxis: { 
                title: { 
                  text: capitalize(widgets.variable),
                  font: { size: 14, color: '#333' }
                },
                gridcolor: 'rgba(128,128,128,0.2)',
                zeroline: false,
                showline: true,
                linecolor: '#ccc',
                tickfont: { size: 12, color: '#666' }
              },
              showlegend: true,
              legend: {
                orientation: 'h',
                y: -0.25,
                x: 0.5,
                xanchor: 'center',
                yanchor: 'top',
                bgcolor: 'rgba(255,255,255,0.95)',
                bordercolor: '#ddd',
                borderwidth: 1,
                font: { size: 10 },
                itemsizing: 'constant',
              },
              hovermode: 'closest',
              hoverdistance: 100,
              spikedistance: 1000,
              title: {
                font: { 
                  size: 18, 
                  color: '#1a73e8',
                  family: 'Arial, sans-serif'
                },
                x: 0.5,
                xanchor: 'center'
              }
            }}
            config={{ 
              responsive: true,
              displayModeBar: true,
              modeBarButtonsToRemove: ['pan2d', 'lasso2d', 'select2d'],
              displaylogo: false,
              toImageButtonOptions: {
                format: 'png',
                filename: 'probabilistic_scores',
                height: 500,
                width: 800,
                scale: 2
              }
            }}
          />
          

        </div>
      )}
    </div>
  );
};

export default ProbabilisticScores; 