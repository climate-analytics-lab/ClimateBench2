import React, { useState, useEffect } from 'react';
import { fetchRMSEData } from '../services/api';
import './Overview.css';

const Overview = () => {
  const [selectedMetric, setSelectedMetric] = useState('rmse');
  const [rmseData, setRmseData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchRMSEData(selectedMetric);
        setRmseData(data);
      } catch (err) {
        setError('Failed to load RMSE data');
        console.error('Failed to load RMSE data:', err);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [selectedMetric]);

  const handleMetricChange = (event) => {
    event.preventDefault();
    const newValue = event.target.value;
    
    // Only update if the value actually changed
    if (newValue !== selectedMetric) {
      setSelectedMetric(newValue);
    }
  };

  const formatMetricName = (metric) => {
    const metricNames = {
      'rmse': 'RMSE',
      'rmse_bias_adjusted': 'RMSE Bias Adjusted',
      'rmse_anomaly': 'RMSE Anomaly'
    };
    return metricNames[metric] || metric;
  };

  const getShortMetricName = (metric) => {
    const shortNames = {
      'rmse': 'RMSE',
      'rmse_bias_adjusted': 'Bias Adj.',
      'rmse_anomaly': 'Anomaly'
    };
    return shortNames[metric] || metric;
  };

  const formatScientificNotation = (value) => {
    const num = Number(value);
    if (isNaN(num)) return 'N/A';
    return num.toExponential(3);
  };

  return (
    <div className="overview">
      <section className="section" id="overview">
        <h2>Overview</h2>
        <p>
          Weather forecasting using machine learning (ML) has seen <a href="https://www.nature.com/articles/s41586-021-03854-z">rapid progress</a> in recent years. 
          WeatherBench is an open framework for evaluating ML and physics-based weather forecasting models in a like-for-like fashion.
        </p>
        
        <p>
          This website contains up-to-date scores of many state-of-the-art global weather models with a focus on medium-range (1-15 day) prediction. 
          In addition, the WeatherBench framework consists of our recently updated <a href="https://github.com/pytorch/weatherbench">WeatherBench-X evaluation code</a> and publicly available, 
          cloud-optimized ground-truth and baseline <a href="https://github.com/pytorch/weatherbench#data">datasets</a>, including a comprehensive copy of the <a href="https://www.ecmwf.int/en/forecasts/datasets/reanalysis-datasets/era5">ERA5</a> dataset used for training most ML models. 
          For more information on how to use the WeatherBench evaluation framework and how to add new models to the benchmark, please check out the <a href="https://github.com/pytorch/weatherbench#documentation">documentation</a>.
        </p>
        
        <p>
          The research community can file a <a href="https://github.com/pytorch/weatherbench/issues">GitHub issue</a> to share ideas and suggestions directly with the WeatherBench 2 team.
        </p>
      </section>

      <section className="section" id="participating-models">
        <h2>Probabilistic Scorecards</h2>

        <div className="metric-controls">
          <label htmlFor="metric-select" className="metric-label">
            Metric:
          </label>
          <select 
            id="metric-select" 
            value={selectedMetric} 
            onChange={handleMetricChange}
            aria-label="Select metric for comparison"
          >
            <option value="rmse">Standard</option>
            <option value="rmse_bias_adjusted">Bias Adjusted</option>
            <option value="rmse_anomaly">Anomaly</option>
          </select>
        </div>

        {loading && (
          <div className="loading" role="status" aria-live="polite">
            <span>Loading {formatMetricName(selectedMetric)} data...</span>
          </div>
        )}
        
        {error && (
          <div className="error" role="alert">
            <strong>Error:</strong> {error}
          </div>
        )}
        
        {!loading && !error && rmseData.length > 0 && (
          <div className="table-container">
            <table 
              className="models-table" 
              id="rmse-table"
              role="table"
              aria-label={`${formatMetricName(selectedMetric)} comparison table for climate models`}
            >
              <caption className="sr-only">
                {formatMetricName(selectedMetric)} comparison for climate models, ranked by performance
              </caption>
              <thead>
                <tr>
                  <th scope="col">Rank</th>
                  <th scope="col">Model</th>
                  <th scope="col">Historical {getShortMetricName(selectedMetric)}</th>
                  <th scope="col">SSP245 {getShortMetricName(selectedMetric)}</th>
                </tr>
              </thead>
              <tbody>
                {rmseData.map((model, index) => (
                  <tr key={model.model} data-rank={index + 1}>
                    <td aria-label={`Rank ${index + 1}`}>{index + 1}</td>
                    <td>
                      <strong>{model.model}</strong>
                    </td>
                    <td aria-label={`Historical ${formatMetricName(selectedMetric)}: ${formatScientificNotation(model.historical)}`}>
                      {formatScientificNotation(model.historical)}
                    </td>
                    <td aria-label={`SSP245 ${formatMetricName(selectedMetric)}: ${formatScientificNotation(model.ssp245)}`}>
                      {formatScientificNotation(model.ssp245)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!loading && !error && rmseData.length === 0 && (
          <div className="no-data" role="status">
            <p>No data available for the selected metric.</p>
          </div>
        )}
      </section>
    </div>
  );
};

export default Overview; 