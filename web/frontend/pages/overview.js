import React, { useState, useEffect } from 'react';

// Helper to parse CSV text into array of objects
function parseCSV(text) {
  const lines = text.trim().split('\n');
  const headers = lines[0].split(',').map(h => h.trim());
  return lines.slice(1).map(line => {
    const values = line.split(',');
    const obj = {};
    headers.forEach((h, i) => {
      obj[h] = values[i];
    });
    return obj;
  });
}

const variableOptions = [
  { value: 'tas', label: 'Temperature (K)' },
  { value: 'pr', label: 'Precipitation (kg/(m2*s))' },
  { value: 'clt', label: 'Cloud Area Fraction (%)' },
  { value: 'od550aer', label: 'Aerosol Optical Depth at 550nm' },
  { value: 'tos', label: 'Sea Surface Temperature (C)' },
];

const metricOptions = [
  { value: 'zonal_mean_rmse', label: 'RMSE' },
  { value: 'zonal_mean_rmse_bias_adjusted', label: 'RMSE Bias Adjusted' },
  { value: 'zonal_mean_rmse_anomaly', label: 'RMSE Anomaly' },
  { value: 'zonal_mean_mae', label: 'MAE' },
  { value: 'zonal_mean_mae_bias_adjusted', label: 'MAE Bias Adjusted' },
  { value: 'zonal_mean_mae_anomaly', label: 'MAE Anomaly' },
];

const periodOptions = [
  { value: 'Historical (1960-2014)', label: '1960-2014' },
  { value: 'Historical (1990-2014)', label: '1990-2014' },
  { value: 'Historical (2005-2014)', label: '2005-2014' },
];

const regionOptions = [
  { value: 'global', label: 'Global' },
  { value: 'northern_hemisphere', label: 'Northern Hemisphere' },
  { value: 'southern_hemisphere', label: 'Southern Hemisphere' },
  { value: 'tropics', label: 'Tropics' },
];

const sortOptions = [
  { value: 'historical', label: 'Historical' },
  { value: 'future', label: 'SSP2-4.5' },
  { value: 'difference', label: 'Difference' },
  { value: 'percent', label: 'Percent Difference' },
];

const futurePeriod = 'SSP2-4.5';
const futureLabel = '2015-2024';
const csvUrl = 'http://localhost:8000/public/benchmark_results.csv';

const Overview = () => {
  const [selectedVariable, setSelectedVariable] = useState('tas');
  const [selectedMetric, setSelectedMetric] = useState('zonal_mean_rmse');
  const [selectedPeriod, setSelectedPeriod] = useState('Historical (2005-2014)');
  const [selectedRegion, setSelectedRegion] = useState('global');
  const [sortBy, setSortBy] = useState('future');
  const [tableData, setTableData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(csvUrl)
      .then(res => res.text())
      .then(text => {
        setTableData(parseCSV(text));
        setLoading(false);
      })
      .catch(err => {
        setError('Failed to load zonal mean RMSE data');
        setLoading(false);
      });
  }, []);

  const filtered = tableData.filter(
    d => d.variable === selectedVariable && d.metric === selectedMetric && d.region === selectedRegion
  );

  // Helper functions for formatting and difference calculations
  const formatScientificNotation = (value) => {
    const num = Number(value);
    if (isNaN(num)) return 'N/A';
    if (Math.abs(num) < 1e-3 || Math.abs(num) > 1e3) {
      return num.toExponential(3);
    }
    return num.toPrecision(4);
  };

  const getDifference = (row) => {
    const futureVal = parseFloat(row[futurePeriod]);
    const histVal = parseFloat(row[selectedPeriod]);
    if (isNaN(futureVal) || isNaN(histVal)) return 'N/A';
    const diff = futureVal - histVal;
    if (Math.abs(diff) < 1e-3 || Math.abs(diff) > 1e3) {
      return diff.toExponential(3);
    }
    return diff.toPrecision(4);
  };

  const getPercentDifference = (row) => {
    const futureVal = parseFloat(row[futurePeriod]);
    const histVal = parseFloat(row[selectedPeriod]);
    if (isNaN(futureVal) || isNaN(histVal) || histVal === 0) return 'N/A';
    const pctDiff = (futureVal - histVal) * 100 / histVal;
    return pctDiff.toPrecision(4);
  };

  // Sorting logic based on sortBy selection
  const sorted = [...filtered].sort((a, b) => {
    let va, vb;
    if (sortBy === 'historical') {
      va = parseFloat(a[selectedPeriod]);
      vb = parseFloat(b[selectedPeriod]);
    } else if (sortBy === 'future') {
      va = parseFloat(a[futurePeriod]);
      vb = parseFloat(b[futurePeriod]);
    } else if (sortBy === 'difference') {
      va = parseFloat(a[futurePeriod]) - parseFloat(a[selectedPeriod]);
      vb = parseFloat(b[futurePeriod]) - parseFloat(b[selectedPeriod]);
    } else if (sortBy === 'percent') {
      const ah = parseFloat(a[selectedPeriod]);
      const bh = parseFloat(b[selectedPeriod]);
      va = ah === 0 ? NaN : ((parseFloat(a[futurePeriod]) - ah) * 100 / ah);
      vb = bh === 0 ? NaN : ((parseFloat(b[futurePeriod]) - bh) * 100 / bh);
    }
    if (isNaN(va)) return 1;
    if (isNaN(vb)) return -1;
    return va - vb;
  });

  return (
    <div className="overview">
      <section className="section" id="overview">
        <h2>Overview</h2>
        <p>
          Add climate bench background and intro.
        </p>
      </section>

      <section className="section" id="portrait-plots">
        <h2>Portrait Plot Results</h2>
        <p>
          Add portrait plot of RMSE results.
        </p>
      </section>

      <section className="section" id="participating-models">
        <h2>Zonal Mean RMSE Table</h2>
        <div className="metric-controls" style={{ display: 'flex', gap: 16, marginBottom: 16, flexWrap: 'wrap' }}>
          <label>
            Variable:&nbsp;
            <select
              value={selectedVariable}
              onChange={e => setSelectedVariable(e.target.value)}
            >
              {variableOptions.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </label>
          <label>
            Metric:&nbsp;
            <select
              value={selectedMetric}
              onChange={e => setSelectedMetric(e.target.value)}
            >
              {metricOptions.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </label>
          <label>
            Historical Period:&nbsp;
            <select
              value={selectedPeriod}
              onChange={e => setSelectedPeriod(e.target.value)}
            >
              {periodOptions.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </label>
          <label>
            Region:&nbsp;
            <select
              value={selectedRegion}
              onChange={e => setSelectedRegion(e.target.value)}
            >
              {regionOptions.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </label>
          <label>
            Sort By:&nbsp;
            <select
              value={sortBy}
              onChange={e => setSortBy(e.target.value)}
            >
              {sortOptions.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </label>
        </div>
        {loading && (
          <div className="loading" role="status" aria-live="polite">
            <span>Loading zonal mean RMSE data...</span>
          </div>
        )}
        {error && (
          <div className="error" role="alert">
            <strong>Error:</strong> {error}
          </div>
        )}
        {!loading && !error && (
          <div className="table-container">
            <table 
              className="models-table" 
              id="zonal-mean-table"
              role="table"
              aria-label="Zonal mean RMSE comparison table for climate models"
            >
              <caption className="sr-only">
                Zonal mean RMSE comparison for climate models, ranked by performance
              </caption>
              <thead>
                <tr>
                  <th scope="col">Rank</th>
                  <th scope="col">Model</th>
                  <th scope="col">Historical</th>
                  <th scope="col">SSP2-4.5</th>
                  <th scope="col">Difference</th>
                  <th scope="col">Percent Difference</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((row, index) => (
                  <tr key={row.model + index}>
                    <td>{index + 1}</td>
                    <td><strong>{row.model}</strong></td>
                    <td>{formatScientificNotation(row[selectedPeriod])}</td>
                    <td>{formatScientificNotation(row[futurePeriod])}</td>
                    <td>{getDifference(row)}</td>
                    <td>{getPercentDifference(row)}</td>
                  </tr>
                ))}
                {sorted.length === 0 && (
                  <tr>
                    <td colSpan={6}>No data available for this selection.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
};

export default Overview;