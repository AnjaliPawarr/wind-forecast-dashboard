
import { useEffect, useState } from "react";
import "./App.css";

const API = "http://127.0.0.1:8000";

function App() {
  const [summary, setSummary] = useState(null);
  const [records, setRecords] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadDashboard() {
      try {
        const [summaryResponse, dataResponse] = await Promise.all([
          fetch(`${API}/api/summary`),
          fetch(`${API}/api/data`),
        ]);

        if (!summaryResponse.ok || !dataResponse.ok) {
          throw new Error("Could not load dashboard data.");
        }

        setSummary(await summaryResponse.json());
        setRecords(await dataResponse.json());
      } catch {
        setError("Could not connect to the backend. Please check that FastAPI is running.");
      }
    }

    loadDashboard();
  }, []);

  if (error) {
    return <main className="page"><p className="error">{error}</p></main>;
  }

  if (!summary) {
    return <main className="page"><p>Loading wind data...</p></main>;
  }

  const chartRecords = records.filter((_, index) => index % 24 === 0);

  const maxValue = Math.max(
    ...chartRecords.map((r) =>
      Math.max(r.actual_generation, r.forecast_generation)
    ),
    1
  );

  return (
    <main className="page">
      <header className="header">
        <div className="brand"><span className="brand-icon">↗</span> WindWise</div>
        <span className="period">JANUARY 2026</span>
      </header>

      <section className="intro">
        <p className="eyebrow">RENEWABLE ENERGY INTELLIGENCE</p>
        <h1>Wind Forecast Portal</h1>
        <p>Understand the gap between predicted and actual wind generation.</p>
      </section>

      <section className="cards">
        <article className="metric">
          <p>Matched hourly periods</p>
          <h2>{summary.matched_periods}</h2>
          <span>January delivery hours</span>
        </article>

        <article className="metric">
          <p>Mean Absolute Error</p>
          <h2>{summary.mae_mw.toLocaleString()} <small>MW</small></h2>
          <span>Average absolute difference</span>
        </article>

        <article className="metric">
          <p>Root Mean Squared Error</p>
          <h2>{summary.rmse_mw.toLocaleString()} <small>MW</small></h2>
          <span>Penalizes larger errors</span>
        </article>

        <article className="metric">
          <p>Forecast Bias</p>
          <h2>{summary.bias_mw > 0 ? "+" : ""}{summary.bias_mw.toLocaleString()} <small>MW</small></h2>
          <span>{summary.bias_mw > 0 ? "Forecasts higher than actuals" : "Forecasts lower than actuals"}</span>
        </article>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">GENERATION PROFILE</p>
            <h2>Forecast vs Actual</h2>
          </div>
          <span className="legend"><i className="actual-dot" /> Actual <i className="forecast-dot" /> Forecast</span>
        </div>

        <div className="chart">
          {chartRecords.map((record) => (
            <div className="bar-group" key={record.startTime} title={`${record.startTime}\nActual: ${record.actual_generation} MW\nForecast: ${record.forecast_generation} MW`}>
              <div className="bars">
                <div className="bar actual-bar" style={{ height: `${record.actual_generation / maxValue * 100}%` }} />
                <div className="bar forecast-bar" style={{ height: `${record.forecast_generation / maxValue * 100}%` }} />
              </div>
              <span>{new Date(record.startTime).getUTCDate()}</span>
            </div>
          ))}
        </div>
        <p className="chart-note">Daily sample of hourly data · Hover over a bar to inspect values · MW</p>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">DATA EXPLORER</p>
            <h2>Hourly comparison</h2>
          </div>
          <span className="period">{records.length} records</span>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Delivery time (UTC)</th>
                <th>Actual (MW)</th>
                <th>Forecast (MW)</th>
                <th>Error (MW)</th>
              </tr>
            </thead>
            <tbody>
              {records.slice(0, 24).map((record) => (
                <tr key={record.startTime}>
                  <td>{new Date(record.startTime).toLocaleString("en-GB", {
                    timeZone: "UTC",
                    day: "2-digit",
                    month: "short",
                    hour: "2-digit",
                    minute: "2-digit",
                    hour12: false,
                  })}</td>
                  <td>{Number(record.actual_generation).toLocaleString()}</td>
                  <td>{Number(record.forecast_generation).toLocaleString()}</td>
                  <td className={record.error >= 0 ? "positive" : "negative"}>
                    {Number(record.error).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="chart-note">Showing the first 24 hourly records.</p>
      </section>

      <footer>
        <p>WindWise · January 2026 analysis</p>
        <p>Cutoff assumption: previous day at 12:00 UTC. Forecast selection requires validation.</p>
        <p>Data source: Elexon BMRS · Wind generation actuals and forecasts</p>
      </footer>
    </main>
  );
}

export default App;
