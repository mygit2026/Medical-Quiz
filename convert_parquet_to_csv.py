"""
Helper to convert `train-00000-of-00001.parquet` to `train.csv` using pyarrow/pandas.
Run locally where `pyarrow` is available:

    python -m venv venv
    venv\Scripts\Activate.ps1
    pip install pyarrow pandas
    python convert_parquet_to_csv.py

This script is optional — it's provided to produce a CSV you can deploy without `pyarrow`.
"""
import os
import pandas as pd

base_path = os.path.dirname(os.path.abspath(__file__))
parquet_path = os.path.join(base_path, "train-00000-of-00001.parquet")
csv_path = os.path.join(base_path, "train.csv")

if not os.path.exists(parquet_path):
    print(f"Parquet file not found: {parquet_path}")
    raise SystemExit(1)

print(f"Reading parquet from {parquet_path} ...")
DF = pd.read_parquet(parquet_path)
print(f"Writing CSV to {csv_path} ...")
DF.to_csv(csv_path, index=False)
print("Done.")
