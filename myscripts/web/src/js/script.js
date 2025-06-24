document.addEventListener("DOMContentLoaded", () => {
  const select = document.getElementById("metric-select");
  const tbody = document.getElementById("rmse-table-body");

  async function fetchAndRender(metric) {
    console.log(`Fetching data for metric: ${metric}`);
    try {
      const response = await fetch(`http://127.0.0.1:8000/rmse-zonal-mean?metric=${metric}`);
      if (!response.ok) throw new Error(`HTTP error ${response.status}`);
      const data = await response.json();

      const models = data.zonal_mean_rmse;
      tbody.innerHTML = "";

      models.forEach((model, index) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${index + 1}</td>
          <td><strong>${model.model}</strong></td>
          <td>${Number(model.historical).toExponential(3)}</td>
          <td>${Number(model.ssp245).toExponential(3)}</td>
        `;
        tbody.appendChild(tr);
      });
    } catch (error) {
      console.error("Failed to load RMSE data:", error);
    }
  }

  // Load initial data
  fetchAndRender(select.value);

  // Add change listener
  select.addEventListener("change", () => {
    console.log("Metric changed to:", select.value);
    fetchAndRender(select.value);
  });
});
