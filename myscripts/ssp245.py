import intake
import pandas as pd
import re

def main():
    # Open the CMIP6 catalog via intake
    catalog_url = "https://storage.googleapis.com/cmip6/pangeo-cmip6.json"
    col = intake.open_esm_datastore(catalog_url)
    df = col.df

    # Filter for ScenarioMIP activity and ssp245 experiment
    ssp245 = df.query("activity_id == 'ScenarioMIP' and experiment_id == 'ssp245'")

    # Keep only ensemble members r1i1p1f1, r2i1p1f1, r3i1p1f1
    pattern = r"r[1-3]i1p1f1"
    ssp245 = ssp245[ssp245["member_id"].str.match(pattern)]

    # Function to filter groups that have all 3 ensemble members
    def has_all_3_members(group):
        required_members = {"r1i1p1f1", "r2i1p1f1", "r3i1p1f1"}
        return required_members.issubset(set(group["member_id"]))

    # Group by model metadata and filter groups having all 3 members
    group_cols = ["institution_id", "source_id", "table_id", "variable_id"]
    filtered = ssp245.groupby(group_cols).filter(has_all_3_members)

    # Define variables of interest (table_id, variable_id)
    variables_of_interest = {
        ("Amon", "tas"), ("Amon", "prc"), ("Amon", "clt"),
        ("Omon", "tos"),
        ("AERmon", "od550aer"),
        ("fx", "areacella"),
        ("Ofx", "areacello")
    }

    # Keep only variables of interest
    filtered = filtered[
        filtered.apply(lambda row: (row["table_id"], row["variable_id"]) in variables_of_interest, axis=1)
    ].copy()

    # Assign priority to grid labels: 'gn' = 0 (highest), 'gr' = 1, others = 2
    filtered["grid_priority"] = filtered["grid_label"].map({"gn": 0, "gr": 1}).fillna(2)

    # Convert version string (e.g. 'v20180712') to integer for sorting
    filtered["version_num"] = filtered["version"].astype(str).str.replace("v", "").astype(int)

    # Sort so we prioritize by model metadata, then grid priority, then latest version
    sort_columns = [
        "institution_id", "source_id", "member_id",
        "table_id", "variable_id", "grid_priority", "version_num"
    ]
    filtered = filtered.sort_values(by=sort_columns, ascending=[True]*6 + [False])

    # Keep only the latest version per unique model/member/variable/table combination
    filtered = filtered.drop_duplicates(
        subset=["institution_id", "source_id", "member_id", "table_id", "variable_id"],
        keep="first"
    )

    # Drop helper columns used for sorting
    for col in ["grid_priority", "version_num", "dcpp_init_year", "experiment_id"]:
        if col in filtered.columns:
            filtered.drop(columns=col, inplace=True)

    # Rename columns for clarity
    filtered = filtered.rename(columns={
        "activity_id": "mip",
        "institution_id": "institution",
        "source_id": "model",
        "member_id": "ensemble",
        "table_id": "realm",
        "variable_id": "variable",
        "grid_label": "grid",
        "version": "version"
    })

    # Save filtered metadata to CSV
    filtered.to_csv("web/ssp245.csv", index=False)
    print("Saved filtered data to web/ssp245.csv")

if __name__ == "__main__":
    main()
