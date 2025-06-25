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
    setSelectedMetric(event.target.value);
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
        <h2>Probabilistic scorecards</h2>

        <label htmlFor="metric-select" className="metric-label">Metric</label>
        <select 
          id="metric-select" 
          value={selectedMetric} 
          onChange={handleMetricChange}
        >
          <option value="rmse">RMSE</option>
          <option value="rmse_bias_adjusted">RMSE Bias Adjusted</option>
          <option value="rmse_anomaly">RMSE Anomaly</option>
        </select>

        {loading && <div className="loading">Loading...</div>}
        {error && <div className="error">{error}</div>}
        
        {!loading && !error && (
          <table className="models-table" id="rmse-table">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Model</th>
                <th>Historical RMSE</th>
                <th>SSP245 RMSE</th>
              </tr>
            </thead>
            <tbody>
              {rmseData.map((model, index) => (
                <tr key={model.model}>
                  <td>{index + 1}</td>
                  <td><strong>{model.model}</strong></td>
                  <td>{Number(model.historical).toExponential(3)}</td>
                  <td>{Number(model.ssp245).toExponential(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
};

export default Overview; 