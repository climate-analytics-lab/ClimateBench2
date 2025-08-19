import pandas as pd
import numpy as np

def aggregate_crps_to_annual(input_file, output_file):
    """
    Aggregate monthly CRPS benchmark data to annual values by taking the mean.
    
    Args:
        input_file (str): Path to the input CSV file with monthly data
        output_file (str): Path to the output CSV file with annual data
    """
    
    # Read the CSV file
    print(f"Reading data from {input_file}...")
    df = pd.read_csv(input_file)
    
    # Convert time column to datetime
    df['time'] = pd.to_datetime(df['time'])
    
    # Clean numeric columns - handle any malformed values
    numeric_columns = ['global', 'northern_hemisphere', 'southern_hemisphere', 'tropics']
    
    for col in numeric_columns:
        # Convert to numeric, coercing errors to NaN
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Check for any NaN values and report them
        nan_count = df[col].isna().sum()
        if nan_count > 0:
            print(f"Warning: Found {nan_count} NaN values in {col} column")
            # Show some examples of problematic rows
            problematic_rows = df[df[col].isna()]
            print(f"Examples of rows with NaN in {col}:")
            print(problematic_rows[['time', 'model_name', 'variable_name', col]].head())
    
    # Remove rows with any NaN values in numeric columns
    initial_rows = len(df)
    df = df.dropna(subset=numeric_columns)
    final_rows = len(df)
    
    if initial_rows != final_rows:
        print(f"Removed {initial_rows - final_rows} rows with missing data")
    
    # Extract year from time column
    df['year'] = df['time'].dt.year
    
    # Group by year, model_name, variable_name, and metric, then calculate mean
    print("Aggregating monthly data to annual values...")
    annual_df = df.groupby(['year', 'model_name', 'variable_name', 'metric']).agg({
        'global': 'mean',
        'northern_hemisphere': 'mean', 
        'southern_hemisphere': 'mean',
        'tropics': 'mean'
    }).reset_index()
    
    # Convert year back to time format (using January 1st of each year)
    annual_df['time'] = pd.to_datetime(annual_df['year'].astype(str) + '-01-01')
    
    # Reorder columns to match original format
    annual_df = annual_df[['time', 'model_name', 'variable_name', 'metric', 
                          'global', 'northern_hemisphere', 'southern_hemisphere', 'tropics']]
    
    # Sort by time, model_name, variable_name
    annual_df = annual_df.sort_values(['time', 'model_name', 'variable_name'])
    
    # Save to CSV
    print(f"Saving annual data to {output_file}...")
    annual_df.to_csv(output_file, index=False)
    
    print(f"Successfully created annual CRPS data with {len(annual_df)} rows")
    print(f"Data covers years {annual_df['time'].dt.year.min()} to {annual_df['time'].dt.year.max()}")
    
    # Print some statistics
    print(f"\nNumber of models: {annual_df['model_name'].nunique()}")
    print(f"Variables: {list(annual_df['variable_name'].unique())}")
    print(f"Years: {sorted(annual_df['time'].dt.year.unique())}")
    
    return annual_df

if __name__ == "__main__":
    input_file = "crps_benchmark_timeseries.csv"
    output_file = "crps_benchmark_timeseries_annual.csv"
    
    annual_data = aggregate_crps_to_annual(input_file, output_file)
    
    # Display first few rows
    print("\nFirst few rows of annual data:")
    print(annual_data.head(10))
