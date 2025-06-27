# Climate Data Visualization with TiTiler

This project integrates TiTiler to serve CMIP6 climate data from Google Cloud Storage and visualize it in an interactive web dashboard.

## 🎯 What is TiTiler?

TiTiler is a modern tile server built on top of FastAPI that can serve raster data (GeoTIFF, NetCDF, etc.) as map tiles. It's perfect for serving climate data because it:

- **Supports NetCDF files** (the standard format for climate data)
- **Handles time series data** (multiple time steps)
- **Works with cloud storage** (Google Cloud Storage, AWS S3, etc.)
- **Provides RESTful APIs** for metadata, bounds, and tiles
- **Supports multiple projections** and resampling methods

## 📁 Project Structure

```
titler/
├── index.html          # Main HTML dashboard
├── styles.css          # CSS styling
├── script.js           # JavaScript functionality
├── titiler_setup.py    # TiTiler setup script
├── start_titiler.sh    # TiTiler startup script
└── README.md           # This file
```

## 🚀 Quick Start

### 1. Set up TiTiler

Run the setup script to install TiTiler and dependencies:

```bash
cd titler
python titiler_setup.py
```

### 2. Start TiTiler Server

```bash
# Option 1: Use the startup script
bash start_titiler.sh

# Option 2: Manual start
uvicorn titiler.main:app --host 0.0.0.0 --port 8000
```

### 3. Open the Dashboard

Open `index.html` in your web browser. The dashboard will automatically connect to TiTiler and display your CMIP6 data.

## 🌍 CMIP6 Data Integration

### Data Source
The application is configured to work with CMIP6 data from Google Cloud Storage:

```
gs://cmip6/CMIP6/ScenarioMIP/IPSL/IPSL-CM6A-LR/ssp245/r1i1p1f1/Amon/pr/gr/v20190119/pr_Amon_IPSL-CM6A-LR_ssp245_r1i1p1f1_gr_201501-210012.nc
```

### Data Details
- **Model**: IPSL-CM6A-LR
- **Scenario**: SSP245
- **Variable**: pr (Precipitation)
- **Frequency**: Monthly (Amon)
- **Time Range**: 2015-2100
- **Grid Resolution**: 1.25° × 1.25°

## 🔧 TiTiler Configuration

### Environment Variables
```bash
export GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR
export GDAL_HTTP_VERSION=2
```

### Key Features
- **Time-based tiling**: Access different time steps via `&time=<index>`
- **Resampling**: Bilinear interpolation for smooth visualization
- **NoData handling**: Proper handling of missing values
- **CORS support**: Cross-origin requests enabled for web applications

## 📊 API Endpoints

Once TiTiler is running, you can access these endpoints:

### Health Check
```
GET http://localhost:8000/health
```

### API Documentation
```
GET http://localhost:8000/docs
```

### Data Information
```
GET http://localhost:8000/info?url=<gcs_path>
```

### Data Bounds
```
GET http://localhost:8000/bounds?url=<gcs_path>
```

### Map Tiles
```
GET http://localhost:8000/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=<gcs_path>&time=<time_index>
```

## 🎮 Interactive Features

### Time Slider
- Navigate through different time steps (2015-2100)
- Synchronized updates across map and plots
- Real-time TiTiler tile updates

### Map Controls
- Layer toggle for CMIP6 data
- Zoom and pan controls
- Automatic bounds fitting

### Data Visualization
- Side-by-side precipitation and temperature plots
- Robinson projection for global view
- Color-coded data representation

## 🔍 Troubleshooting

### TiTiler Not Starting
```bash
# Check if port 8000 is available
lsof -i :8000

# Kill existing process if needed
kill -9 <PID>
```

### Data Not Loading
1. Verify Google Cloud Storage access
2. Check TiTiler logs for errors
3. Ensure NetCDF file path is correct
4. Verify file permissions

### CORS Issues
If you see CORS errors in the browser console:
1. Check TiTiler CORS configuration
2. Ensure TiTiler is running on the correct host
3. Verify the HTML file is being served from a web server

## 🛠️ Development

### Adding New Data Sources
1. Update the `gcsPath` in `script.js`
2. Modify the metadata structure if needed
3. Update the time range and variable information

### Customizing Visualizations
1. Modify Plotly configurations in `script.js`
2. Update CSS styles in `styles.css`
3. Add new interactive controls as needed

### Extending TiTiler
1. Create custom TiTiler endpoints
2. Add data preprocessing functions
3. Implement caching for better performance

## 📚 Resources

- [TiTiler Documentation](https://developmentseed.org/titiler/)
- [CMIP6 Data Access](https://pcmdi.llnl.gov/CMIP6/)
- [Google Cloud Storage](https://cloud.google.com/storage)
- [Leaflet.js](https://leafletjs.com/)
- [Plotly.js](https://plotly.com/javascript/)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with TiTiler
5. Submit a pull request

## 📄 License

This project is open source and available under the MIT License. 