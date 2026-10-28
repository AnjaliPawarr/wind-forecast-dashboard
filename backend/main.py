
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Wind Forecast Portal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://wind-forecast-dashboard-1-070j.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = Path(__file__).parent / "wind_comparison_january_2026.csv"


def load_data():
    if not DATA_FILE.exists():
        raise HTTPException(
            status_code=404,
            detail="Comparison CSV not found. Run compare_wind.py first.",
        )

    df = pd.read_csv(DATA_FILE)
    df = df.where(pd.notna(df), None)
    return df


@app.get("/")
def home():
    return {"message": "Wind Forecast Portal API is running"}


@app.get("/api/summary")
def get_summary():
    df = load_data()

    errors = df["error"].dropna()
    if errors.empty:
        raise HTTPException(
            status_code=500,
            detail="No valid error data available",
        )

    return {
        "month": "January 2026",
        "matched_periods": int(len(df)),
        "mae_mw": round(float(errors.abs().mean()), 2),
        "rmse_mw": round(float((errors.pow(2).mean()) ** 0.5), 2),
        "bias_mw": round(float(errors.mean()), 2),
        "forecast_cutoff": "Previous day at 12:00 UTC (assumption)",
    }


@app.get("/api/data")
def get_data():
    df = load_data()
    return df.to_dict(orient="records")
