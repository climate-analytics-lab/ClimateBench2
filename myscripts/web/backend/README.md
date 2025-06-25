# ClimateBench 2.0 Backend

This directory contains two FastAPI applications:
- `index.py` for RMSE/Overview endpoints (port 8000)
- `probabilistic-scores.py` for Probabilistic Scores endpoints (port 8001)

## Setup

1. Create and activate your environment:
   ```bash
   conda create -n climatebench python=3.10
   conda activate climatebench
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up Google Cloud credentials:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/service-account-key.json"
   ```

4. Start the servers:
   ```bash
   uvicorn index:app --reload --host 127.0.0.1 --port 8000
   uvicorn probabilistic-scores:app --reload --host 127.0.0.1 --port 8001
   ```

## API Docs

- [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs) 