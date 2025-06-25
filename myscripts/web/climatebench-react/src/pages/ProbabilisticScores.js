import React, { useState, useEffect, useRef, useCallback } from 'react';
import Plot from 'react-plotly.js';
import { fetchVariableData } from '../services/api';
import './ProbabilisticScores.css';

const ProbabilisticScores = () => {
  const [widgets, setWidgets] = useState({
    variable: 'pr',
    metric: 'mae',
    level: 'surface',
    region: 'global',
    year: '2020',
    resolution: 'low'
  });
  
  const [chartData, setChartData] = useState([]);
  const [chartLayout, setChartLayout] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [stats, setStats] = useState({
    bestCRPS: '0.847',
    modelsCompared: '5',
    forecastDays: '15',
    evaluationDays: '365'
  });

  const chartContainerRef = useRef(null);

  const capitalize = (str) => {
    return str.charAt(0).toUpperCase() + str.slice(1);
  };

  const fetchAndPlotVariable = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const data = await fetchVariableData(widgets.variable);

      if (data.error) {
        setError(data.error);
        return;
      }

      const observedColor = 'royalblue';
      const modelColor = 'rgba(128, 128, 128, 0.3)';

      const traces = [
        {
          x: data.time,
          y: data[widgets.variable],
          type: "scatter",
          mode: "lines",
          name: "Observed",
          line: { width: 3, color: observedColor },
          hovertemplate: 'Time: %{x}<br>Value: %{y}<extra>Observed</extra>',
        },
      ];

      if (data.predicted) {
        for (const [modelName, predData] of Object.entries(data.predicted)) {
          traces.push({
            x: predData.time,
            y: predData.values,
            type: "scatter",
            mode: "lines",
            name: modelName,
            line: {
              width: 1.5,
              color: modelColor,
              dash: 'dot',
            },
            hovertemplate: 'Time: %{x}<br>Predicted: %{y}<extra>' + modelName + '</extra>',
          });
        }
      }

      setChartData(traces);
      setChartLayout(layout => ({
        ...layout,
        title: {
          text: `📈 Global Average ${widgets.variable.toUpperCase()} Over Time`,
          font: { size: 20, family: "Arial" },
        }
      }));
    } catch (err) {
      console.error("Failed to fetch data:", err);
      setError('Failed to load data');
    } finally {
      setLoading(false);
    }
  }, [widgets.variable]);

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
    fetchAndPlotVariable();
    updateChart();
  }, [fetchAndPlotVariable, updateChart]);

  // Simulate real-time data updates
  useEffect(() => {
    const interval = setInterval(() => {
      setStats(prev => ({
        ...prev,
        bestCRPS: (Math.random() * 0.3 + 0.7).toFixed(3)
      }));
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="probabilistic-scores">
      <h1 className="page-title">Probabilistic Scores</h1>

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
              <option value="mae">Mean Absolute Error (MAE)</option>
              <option value="rmse">Root Mean Squared Error (RMSE)</option>
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
              <option value="extratropics">Extratropics (&lt;20°S or &gt;20°N)</option>
              <option value="northern_hemisphere">Northern Hemisphere</option>
              <option value="southern_hemisphere">Southern Hemisphere</option>
              <option value="arctic">Arctic (&gt;66.5°N)</option>
              <option value="polar">Polar regions</option>
              <option value="europe">Europe</option>
              <option value="north_america">North America</option>
              <option value="asia">Asia</option>
              <option value="africa">Africa</option>
              <option value="australia">Australia</option>
              <option value="south_america">South America</option>
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
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
          </div>
        </div>

        <h2 className="chart-title">
          {widgets.metric.toUpperCase()} for {widgets.variable.charAt(0).toUpperCase() + widgets.variable.slice(1)} at {widgets.level === "surface" ? "Surface" : `${widgets.level} hPa`} - {widgets.region.charAt(0).toUpperCase() + widgets.region.slice(1).replace(/_/g, " ")} ({widgets.year})
        </h2>
        
        {loading && <div className="chart-placeholder">🔄 Loading...</div>}
        {error && <div className="chart-placeholder" style={{color: 'red'}}>❌ {error}</div>}
        
        {!loading && !error && (
          <div ref={chartContainerRef} style={{width: '100%', height: '500px'}}>
            <Plot
              data={chartData}
              layout={chartLayout}
              config={{responsive: true}}
              style={{width: '100%', height: '100%'}}
            />
          </div>
        )}
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-value">{stats.bestCRPS}</div>
          <div className="stat-label">Best CRPS Score</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.modelsCompared}</div>
          <div className="stat-label">Models Compared</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.forecastDays}</div>
          <div className="stat-label">Forecast Days</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{stats.evaluationDays}</div>
          <div className="stat-label">Evaluation Days</div>
        </div>
      </div>

      <div className="info-box">
        <h3>About Probabilistic Metrics</h3>
        <p>
          <strong>CRPS (Continuous Ranked Probability Score):</strong> Measures the
          difference between the forecast probability distribution and the observed
          value. Lower scores indicate better performance.
        </p>
        <p>
          <strong>RMSE (Root Mean Squared Error):</strong> Measures the average
          magnitude of forecast errors. Lower RMSE indicates more accurate predictions.
        </p>
        <p>
          <strong>MAE (Mean Absolute Error):</strong> Represents the average absolute
          difference between predicted and observed values. Lower MAE means better
          accuracy.
        </p>
      </div>
    </div>
  );
};

export default ProbabilisticScores; 