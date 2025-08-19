#!/usr/bin/env python3
"""
Combine all tos CRPS timeseries results and add them to crps_benchmark_timeseries.csv
"""

import pandas as pd
import glob
import os

def combine_tos_results():
    """
    Combine all tos CRPS timeseries results and add to main timeseries file.
    """
    print("🔧 Combining all tos CRPS timeseries results...")
    
    # List of all tos files
    tos_files = [
        "tos_crps_timeseries_ACCESS_CM2_all_regions.csv",
        "tos_crps_timeseries_CanESM5_all_regions.csv",
        "tos_crps_timeseries_CESM2_WACCM_all_regions.csv",
        "tos_crps_timeseries_EC_Earth3_Veg_LR_all_regions.csv",
        "tos_crps_timeseries_FGOALS_g3_all_regions.csv",
        "tos_crps_timeseries_FIO_ESM_2_0_all_regions.csv",
        "tos_crps_timeseries_GFDL_ESM4_all_regions.csv",
        "tos_crps_timeseries_IPSL_CM6A_LR_all_regions.csv",
        "tos_crps_timeseries_MIROC6_all_regions.csv",
        "tos_crps_timeseries_MPI_ESM1_2_LR_all_regions.csv",
        "tos_crps_timeseries_NorESM2_LM_all_regions.csv"
    ]
    
    # Load existing timeseries file
    print("📊 Loading existing crps_benchmark_timeseries.csv...")
    try:
        existing_df = pd.read_csv("crps_benchmark_timeseries.csv")
        print(f"✅ Loaded existing file with {len(existing_df)} records")
    except FileNotFoundError:
        print("❌ crps_benchmark_timeseries.csv not found")
        return
    
    # Combine all tos files
    all_tos_data = []
    
    for file in tos_files:
        if os.path.exists(file):
            print(f"📄 Processing {file}...")
            try:
                df = pd.read_csv(file)
                all_tos_data.append(df)
                print(f"✅ Added {len(df)} records from {file}")
            except Exception as e:
                print(f"❌ Error reading {file}: {e}")
        else:
            print(f"⚠️  File not found: {file}")
    
    if not all_tos_data:
        print("❌ No tos data files found")
        return
    
    # Combine all tos data
    print("🔗 Combining all tos data...")
    combined_tos_df = pd.concat(all_tos_data, ignore_index=True)
    print(f"✅ Combined {len(combined_tos_df)} tos records")
    
    # Remove any existing tos records from the main file
    print("🧹 Removing existing tos records from main file...")
    existing_without_tos = existing_df[existing_df['variable_name'] != 'tos']
    print(f"✅ Kept {len(existing_without_tos)} non-tos records")
    
    # Combine existing data with new tos data
    print("🔗 Adding tos data to main file...")
    final_df = pd.concat([existing_without_tos, combined_tos_df], ignore_index=True)
    print(f"✅ Final file has {len(final_df)} total records")
    
    # Save the updated file
    output_file = "crps_benchmark_timeseries.csv"
    final_df.to_csv(output_file, index=False)
    print(f"💾 Updated {output_file} with {len(combined_tos_df)} new tos records")
    
    # Show summary
    print("\n📊 Summary:")
    print(f"   Original records: {len(existing_df)}")
    print(f"   Non-tos records kept: {len(existing_without_tos)}")
    print(f"   New tos records added: {len(combined_tos_df)}")
    print(f"   Final total records: {len(final_df)}")
    
    # Show breakdown by variable
    print("\n📈 Records by variable:")
    var_counts = final_df['variable_name'].value_counts()
    for var, count in var_counts.items():
        print(f"   {var}: {count}")
    
    # Show breakdown by model for tos
    tos_data = final_df[final_df['variable_name'] == 'tos']
    if len(tos_data) > 0:
        print("\n🌊 TOS records by model:")
        model_counts = tos_data['model_name'].value_counts()
        for model, count in model_counts.items():
            print(f"   {model}: {count}")
    
    return output_file

if __name__ == "__main__":
    combine_tos_results()
