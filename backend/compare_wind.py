
import requests
import pandas as pd
import numpy as np

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH"
HISTORY_URL = (
    "https://data.elexon.co.uk/bmrs/api/v1/"
    "forecast/generation/wind/history"
)


def get_records(url, params):
    response = requests.get(url, params=params, timeout=60)
    print("Status:", response.status_code)
    response.raise_for_status()

    data = response.json()
    return data.get("data", []) if isinstance(data, dict) else data


def fetch_actuals():
    records = []
    current = pd.Timestamp("2026-01-01")
    last = pd.Timestamp("2026-01-31")

    while current <= last:
        batch_end = min(
            current + pd.Timedelta(days=6), last
        )
        print(f"Fetching actuals: {current.date()} to {batch_end.date()}")

        batch = get_records(
            BASE_URL,
            {
                "settlementDateFrom": current.strftime("%Y-%m-%d"),
                "settlementDateTo": batch_end.strftime("%Y-%m-%d"),
            },
        )

        records.extend(
            r for r in batch
            if r.get("fuelType") == "WIND"
            and str(r.get("startTime", "")).startswith("2026-01")
        )

        current = batch_end + pd.Timedelta(days=1)

    df = pd.DataFrame(records)
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["generation"] = pd.to_numeric(df["generation"], errors="coerce")

    # Convert half-hour actuals to hourly average generation.
    df["hour"] = df["startTime"].dt.floor("h")

    hourly = (
        df.groupby("hour", as_index=False)["generation"]
        .mean()
        .rename(columns={
            "hour": "startTime",
            "generation": "actual_generation",
        })
    )

    return hourly


def fetch_historical_forecasts():
    records = []

    for day in pd.date_range("2026-01-01", "2026-01-31", freq="D"):
        # Assumption: day-ahead decision cutoff = previous day at 12:00 UTC.
        cutoff = day - pd.Timedelta(days=1) + pd.Timedelta(hours=12)

        print(f"Fetching forecast for {day.date()} at cutoff {cutoff} UTC")

        try:
            batch = get_records(
                HISTORY_URL,
                {"publishTime": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")},
            )
        except requests.RequestException as error:
            print("Forecast request failed:", error)
            continue

        for record in batch:
            start_time = pd.to_datetime(
                record.get("startTime"), utc=True, errors="coerce"
            )
            publish_time = pd.to_datetime(
                record.get("publishTime"), utc=True, errors="coerce"
            )

            if pd.isna(start_time) or pd.isna(publish_time):
                continue

            # Keep only the target delivery day and eligible publications.
            if (
                    start_time.date() == day.date()
                    and publish_time <= cutoff.tz_localize("UTC")
            ):
                records.append(record)

    if not records:
        return pd.DataFrame(
            columns=["startTime", "publishTime", "forecast_generation"]
        )

    df = pd.DataFrame(records)
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    df["generation"] = pd.to_numeric(df["generation"], errors="coerce")

    df = df.sort_values("publishTime")
    df = df.drop_duplicates("startTime", keep="last")

    return df.rename(
        columns={"generation": "forecast_generation"}
    )[["startTime", "publishTime", "forecast_generation"]]


def main():
    actuals = fetch_actuals()
    print("\nHourly actual records:", len(actuals))

    forecasts = fetch_historical_forecasts()
    print("Eligible historical forecast records:", len(forecasts))

    comparison = actuals.merge(
        forecasts, on="startTime", how="inner"
    ).dropna(subset=["actual_generation", "forecast_generation"])

    if comparison.empty:
        print("\nNo matching records found.")
        print("We need to inspect the history endpoint's date coverage.")
        return

    comparison["error"] = (
            comparison["forecast_generation"]
            - comparison["actual_generation"]
    )

    mae = comparison["error"].abs().mean()
    rmse = np.sqrt((comparison["error"] ** 2).mean())
    bias = comparison["error"].mean()

    comparison.to_csv("wind_comparison_january_2026.csv", index=False)

    print("\n--- January 2026 comparison ---")
    print("Matched hourly periods:", len(comparison))
    print(f"MAE:  {mae:.2f} MW")
    print(f"RMSE: {rmse:.2f} MW")
    print(f"Bias: {bias:.2f} MW")
    print("Saved: wind_comparison_january_2026.csv")


if __name__ == "__main__":
    main()


