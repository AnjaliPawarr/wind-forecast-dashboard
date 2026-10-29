import requests
import pandas as pd
import numpy as np

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH"
HISTORY_URL = (
    "https://data.elexon.co.uk/bmrs/api/v1/"
    "forecast/generation/wind/history"
)

START_DATE = "2026-01-01"
END_DATE = "2026-01-31"
OUTPUT_FILE = "wind_comparison_january_2026.csv"
REQUEST_TIMEOUT = 60


def get_records(url, params):
    """Fetch records from an Elexon endpoint and normalize common response shapes."""
    response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    print(f"HTTP {response.status_code}: {response.url}")
    response.raise_for_status()

    payload = response.json()
    if isinstance(payload, dict):
        records = payload.get("data", [])
        if isinstance(records, list):
            return records
        raise ValueError("Unexpected API response: 'data' is not a list.")
    if isinstance(payload, list):
        return payload
    raise ValueError("Unexpected API response format.")


def fetch_actuals():
    """Fetch January WIND actuals and aggregate half-hour records to hourly means."""
    records = []
    current = pd.Timestamp(START_DATE)
    last = pd.Timestamp(END_DATE)

    while current <= last:
        batch_end = min(current + pd.Timedelta(days=6), last)
        print(f"Fetching actuals: {current.date()} to {batch_end.date()}")

        batch = get_records(
            BASE_URL,
            {
                "settlementDateFrom": current.strftime("%Y-%m-%d"),
                "settlementDateTo": batch_end.strftime("%Y-%m-%d"),
            },
        )

        records.extend(
            record
            for record in batch
            if record.get("fuelType") == "WIND"
            and str(record.get("startTime", "")).startswith("2026-01")
        )
        current = batch_end + pd.Timedelta(days=1)

    if not records:
        raise RuntimeError("No January 2026 WIND actual records returned.")

    df = pd.DataFrame(records)
    required = {"startTime", "generation"}
    if not required.issubset(df.columns):
        raise RuntimeError(f"Actual data is missing columns: {required - set(df.columns)}")

    df["startTime"] = pd.to_datetime(df["startTime"], utc=True, errors="coerce")
    df["generation"] = pd.to_numeric(df["generation"], errors="coerce")
    df = df.dropna(subset=["startTime", "generation"])
    df = df[df["startTime"].dt.strftime("%Y-%m") == "2026-01"]

    # Keep one row per half-hour startTime before hourly aggregation.
    duplicate_actuals = int(df.duplicated(subset=["startTime"]).sum())
    if duplicate_actuals:
        print(f"WARNING: {duplicate_actuals} duplicate actual startTime rows found.")
        # Repeated identical settlement rows can otherwise overweight the hourly mean.
        df = df.groupby("startTime", as_index=False)["generation"].mean()

    df["hour"] = df["startTime"].dt.floor("h")
    hourly = (
        df.groupby("hour", as_index=False)["generation"]
        .mean()
        .rename(
            columns={
                "hour": "startTime",
                "generation": "actual_generation",
            }
        )
        .sort_values("startTime")
        .reset_index(drop=True)
    )

    expected_hours = pd.date_range(
        f"{START_DATE} 00:00:00",
        f"{END_DATE} 23:00:00",
        freq="h",
        tz="UTC",
    )
    present = pd.DatetimeIndex(hourly["startTime"])
    missing = expected_hours.difference(present)

    print("\n--- Actual coverage validation ---")
    print("Raw half-hour WIND rows:", len(df))
    print("Hourly actual rows:", len(hourly))
    print("First actual hour:", hourly["startTime"].min())
    print("Last actual hour:", hourly["startTime"].max())
    print("Missing hourly actuals:", len(missing))
    if len(missing):
        print("First missing actual hours:", list(missing[:10]))

    return hourly


def fetch_historical_forecasts():
    """
    Query historical wind forecasts for each delivery day.

    The chosen decision cutoff is an explicit assignment assumption:
    12:00 UTC on the previous calendar day. The history endpoint is queried
    at that publication time, then records are filtered to the delivery day
    and publishTime <= cutoff. If the endpoint returns multiple eligible
    versions, the latest publication per delivery timestamp is selected.
    """
    all_records = []

    for day in pd.date_range(START_DATE, END_DATE, freq="D", tz="UTC"):
        cutoff = day - pd.Timedelta(days=1) + pd.Timedelta(hours=12)
        cutoff = cutoff.tz_convert("UTC")
        cutoff_text = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

        print(f"\nFetching forecast for delivery day {day.date()} at cutoff {cutoff_text}")

        try:
            batch = get_records(HISTORY_URL, {"publishTime": cutoff_text})
        except (requests.RequestException, ValueError) as error:
            print(f"ERROR: Forecast request failed for {day.date()}: {error}")
            continue

        print("Raw forecast records returned:", len(batch))

        for record in batch:
            start_time = pd.to_datetime(
                record.get("startTime"), utc=True, errors="coerce"
            )
            publish_time = pd.to_datetime(
                record.get("publishTime"), utc=True, errors="coerce"
            )
            generation = pd.to_numeric(record.get("generation"), errors="coerce")

            if pd.isna(start_time) or pd.isna(publish_time) or pd.isna(generation):
                continue

            # The target delivery date must match exactly.
            if start_time.date() != day.date():
                continue

            # Do not use information published after the assumed decision cutoff.
            if publish_time > cutoff:
                continue

            item = dict(record)
            item["startTime"] = start_time
            item["publishTime"] = publish_time
            item["forecast_generation"] = float(generation)
            item["decision_cutoff"] = cutoff
            all_records.append(item)

    columns = [
        "startTime",
        "publishTime",
        "forecast_generation",
        "decision_cutoff",
    ]
    if not all_records:
        print("\nWARNING: No eligible forecast records were returned.")
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(all_records)
    df = df.dropna(subset=["startTime", "publishTime", "forecast_generation"])
    df = df.sort_values(["startTime", "publishTime"])

    # Select the most recent eligible publication per delivery timestamp.
    # This only works among records actually returned by the API.
    df = df.drop_duplicates(subset=["startTime"], keep="last")
    df = df[columns].sort_values("startTime").reset_index(drop=True)

    expected_hours = pd.date_range(
        f"{START_DATE} 00:00:00",
        f"{END_DATE} 23:00:00",
        freq="h",
        tz="UTC",
    )
    present = pd.DatetimeIndex(df["startTime"])
    missing = expected_hours.difference(present)

    print("\n--- Forecast coverage validation ---")
    print("Eligible forecast rows:", len(df))
    print("Unique delivery timestamps:", df["startTime"].nunique())
    print("Unique publication timestamps:", df["publishTime"].nunique())
    print("First publication time:", df["publishTime"].min())
    print("Last publication time:", df["publishTime"].max())
    print("First delivery hour:", df["startTime"].min())
    print("Last delivery hour:", df["startTime"].max())
    print("Missing hourly forecasts:", len(missing))
    if len(missing):
        print("First missing forecast hours:", list(missing[:10]))

    # Explicitly flag publication-time patterns that warrant manual inspection.
    publication_counts = df.groupby(df["startTime"].dt.date)["publishTime"].nunique()
    print("Publication versions per delivery day (min/max):",
          int(publication_counts.min()), int(publication_counts.max()))
    if (publication_counts <= 1).all():
        print(
            "NOTE: Only one publication timestamp per delivery day was retained. "
            "Verify that the API query returns the intended latest eligible "
            "forecast for the assignment's decision cutoff."
        )

    return df


def main():
    actuals = fetch_actuals()
    forecasts = fetch_historical_forecasts()

    if actuals.empty:
        raise RuntimeError("Actual data is empty; cannot compare.")
    if forecasts.empty:
        raise RuntimeError("Forecast data is empty; cannot compare.")

    comparison = actuals.merge(
        forecasts,
        on="startTime",
        how="inner",
        validate="one_to_one",
    ).dropna(subset=["actual_generation", "forecast_generation"])

    if comparison.empty:
        raise RuntimeError(
            "No matching hourly records found. Check Elexon endpoint response "
            "and timestamp conventions."
        )

    comparison["error"] = (
            comparison["forecast_generation"] - comparison["actual_generation"]
    )
    comparison["absolute_error"] = comparison["error"].abs()
    comparison["delivery_date"] = comparison["startTime"].dt.strftime("%Y-%m-%d")
    comparison["hour_utc"] = comparison["startTime"].dt.hour

    errors = comparison["error"]
    absolute_errors = errors.abs()
    mae = float(absolute_errors.mean())
    rmse = float(np.sqrt((errors ** 2).mean()))
    bias = float(errors.mean())
    p90 = float(absolute_errors.quantile(0.90))
    p95 = float(absolute_errors.quantile(0.95))

    expected_hours = pd.date_range(
        f"{START_DATE} 00:00:00",
        f"{END_DATE} 23:00:00",
        freq="h",
        tz="UTC",
    )
    missing_comparison = expected_hours.difference(
        pd.DatetimeIndex(comparison["startTime"])
    )

    comparison.to_csv(OUTPUT_FILE, index=False)

    # Error grouped by delivery hour (UTC) for a more useful risk breakdown.
    hourly_error = (
        comparison.groupby("hour_utc")
        .agg(
            sample_count=("error", "size"),
            mae_mw=("error", lambda values: values.abs().mean()),
            bias_mw=("error", "mean"),
            p90_abs_error_mw=("absolute_error", lambda values: values.quantile(0.90)),
            p95_abs_error_mw=("absolute_error", lambda values: values.quantile(0.95)),
        )
        .round(2)
    )
    hourly_error.to_csv("wind_error_by_hour_january_2026.csv")

    print("\n--- January 2026 comparison ---")
    print("Matched hourly periods:", len(comparison))
    print("Expected hourly periods:", len(expected_hours))
    print("Missing comparison hours:", len(missing_comparison))
    print(f"MAE:                 {mae:.2f} MW")
    print(f"RMSE:                {rmse:.2f} MW")
    print(f"Bias (forecast-actual): {bias:.2f} MW")
    print(f"P90 absolute error:  {p90:.2f} MW")
    print(f"P95 absolute error:  {p95:.2f} MW")
    print("Saved comparison:", OUTPUT_FILE)
    print("Saved hourly error breakdown: wind_error_by_hour_january_2026.csv")

    print("\nFirst 5 matched records:")
    print(
        comparison[
            [
                "startTime",
                "actual_generation",
                "publishTime",
                "decision_cutoff",
                "forecast_generation",
                "error",
            ]
        ].head().to_string(index=False)
    )

    if len(comparison) != len(expected_hours):
        print(
            "\nWARNING: Comparison does not contain all 744 expected hours. "
            "Do not treat monthly metrics as complete until missing coverage "
            "is explained."
        )
    if (comparison["publishTime"] > comparison["decision_cutoff"]).any():
        print(
            "ERROR: Some selected forecasts were published after the decision "
            "cutoff. Investigate before using the metrics."
        )


if __name__ == "__main__":
    main()
