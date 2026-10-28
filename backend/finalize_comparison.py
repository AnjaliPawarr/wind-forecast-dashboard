
import pandas as pd
import numpy as np

actuals = pd.read_json("wind_actuals_january_2026.json")
forecasts = pd.read_csv("validated_wind_forecasts_january_2026.csv")

actuals["startTime"] = pd.to_datetime(actuals["startTime"], utc=True)
forecasts["startTime"] = pd.to_datetime(forecasts["startTime"], utc=True)

actuals["generation"] = pd.to_numeric(
    actuals["generation"], errors="coerce"
)

actuals["hour"] = actuals["startTime"].dt.floor("h")

hourly_actuals = (
    actuals.groupby("hour", as_index=False)["generation"]
    .mean()
    .rename(columns={
        "hour": "startTime",
        "generation": "actual_generation",
    })
)

forecasts["generation"] = pd.to_numeric(
    forecasts["generation"], errors="coerce"
)

forecasts = forecasts.rename(
    columns={"generation": "forecast_generation"}
)

comparison = hourly_actuals.merge(
    forecasts[["startTime", "publishTime", "forecast_generation"]],
    on="startTime",
    how="inner",
)

comparison = comparison.dropna(
    subset=["actual_generation", "forecast_generation"]
)

comparison["error"] = (
        comparison["forecast_generation"] - comparison["actual_generation"]
)

mae = comparison["error"].abs().mean()
rmse = np.sqrt((comparison["error"] ** 2).mean())
bias = comparison["error"].mean()

comparison.to_csv("wind_comparison_january_2026.csv", index=False)

print("Matched hourly periods:", len(comparison))
print(f"MAE:  {mae:.2f} MW")
print(f"RMSE: {rmse:.2f} MW")
print(f"Bias: {bias:.2f} MW")
print("Saved: wind_comparison_january_2026.csv")
