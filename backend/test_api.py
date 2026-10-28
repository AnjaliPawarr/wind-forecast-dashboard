
import requests
import pandas as pd

URL = (
    "https://data.elexon.co.uk/bmrs/api/v1/"
    "forecast/generation/wind/history"
)

all_records = []
daily_results = []

for day in pd.date_range("2026-01-01", "2026-01-31", freq="D"):
    cutoff = day - pd.Timedelta(days=1) + pd.Timedelta(hours=12)

    response = requests.get(
        URL,
        params={
            "publishTime": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        },
        timeout=60,
    )

    print("Status:", response.status_code, "| Date:", day.date())
    response.raise_for_status()

    data = response.json()
    records = data.get("data", [])

    if not records:
        daily_results.append((str(day.date()), 0, "NO DATA"))
        continue

    df = pd.DataFrame(records)
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)

    day_start = pd.Timestamp(day.date(), tz="UTC")
    day_end = day_start + pd.Timedelta(days=1)
    cutoff = cutoff.tz_localize("UTC")

    eligible = df[
        (df["startTime"] >= day_start)
        & (df["startTime"] < day_end)
        & (df["publishTime"] <= cutoff)
        ].copy()

    eligible = eligible.sort_values("publishTime")
    eligible = eligible.drop_duplicates("startTime", keep="last")

    count = len(eligible)
    status = "OK" if count == 24 else f"CHECK ({count}/24)"

    daily_results.append((str(day.date()), count, status))
    all_records.extend(eligible.to_dict(orient="records"))

print("\n--- DAILY VALIDATION ---")
for day, count, status in daily_results:
    print(f"{day}: {count} hourly records — {status}")

print("\nTotal eligible records:", len(all_records))
print("Days with 24 records:", sum(1 for _, count, _ in daily_results if count == 24))
print("Days needing review:", sum(1 for _, count, _ in daily_results if count != 24))

if all_records:
    result = pd.DataFrame(all_records)
    result.to_csv("validated_wind_forecasts_january_2026.csv", index=False)
    print("Saved: validated_wind_forecasts_january_2026.csv")
