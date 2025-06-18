// Widget interactions
const widgets = {
    variable: document.getElementById('variable-select'),
    metric: document.getElementById('metric-select'),
    level: document.getElementById('level-select'),
    region: document.getElementById('region-select'),
    year: document.getElementById('year-select'),
    resolution: document.getElementById('resolution-select'),
    comparisonModel: document.getElementById('comparison-model'),
    toggleMarkers: document.getElementById('toggle-markers')
};

const chartTitle = document.querySelector('.chart-title');
const chartPlaceholder = document.querySelector('.chart-placeholder');

// Update chart title based on selections
function updateChart() {
    const variable = widgets.variable.value.charAt(0).toUpperCase() + widgets.variable.value.slice(1);
    const metric = widgets.metric.value.toUpperCase();
    const level = widgets.level.value === 'surface' ? 'Surface' : `${widgets.level.value} hPa`;
    const region = widgets.region.value.charAt(0).toUpperCase() + widgets.region.value.slice(1).replace('_', ' ');
    const year = widgets.year.value;

    chartTitle.textContent = `${metric} for ${variable} at ${level} - ${region} (${year})`;
    
    // Simulate loading
    chartPlaceholder.innerHTML = '<p style="color: #1a73e8;">🔄 Loading chart data...</p>';
    setTimeout(() => {
        chartPlaceholder.innerHTML = `
            <p>📊 Interactive chart will be displayed here</p>
            <p style="margin-top: 10px; font-size: 0.9em;">Chart updates based on selected parameters above</p>
        `;
    }, 1000);
}

// Add event listeners to all select elements
Object.values(widgets).forEach(widget => {
    if (widget && widget.tagName === 'SELECT') {
        widget.addEventListener('change', updateChart);
    }
});

// Radio button handling
const radioButtons = document.querySelectorAll('input[name="mode"]');
const comparisonInput = widgets.comparisonModel;

radioButtons.forEach(radio => {
    radio.addEventListener('change', function() {
        if (this.value === 'compare') {
            comparisonInput.style.opacity = '1';
            comparisonInput.disabled = false;
        } else {
            comparisonInput.style.opacity = '0.5';
            comparisonInput.disabled = true;
        }
        updateChart();
    });
});

// Toggle switch handling
widgets.toggleMarkers.addEventListener('click', function() {
    this.classList.toggle('off');
    updateChart();
});

// Initialize disabled state for comparison input
comparisonInput.style.opacity = '0.5';
comparisonInput.disabled = true;

// Smooth scrolling for navigation links
document.querySelectorAll('.nav-links a').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        // Since this is a separate page, we'd normally navigate
        // For demo purposes, we'll just highlight the active link
        document.querySelectorAll('.nav-links a').forEach(link => link.classList.remove('active'));
        this.classList.add('active');
    });
});

// Simulate real-time data updates
setInterval(() => {
    const statValues = document.querySelectorAll('.stat-value');
    statValues[0].textContent = (Math.random() * 0.3 + 0.7).toFixed(3);
}, 5000);
