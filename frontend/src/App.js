import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import './App.css';

function App() {
  const [simData, setSimData] = useState(null);
  const [isRunning, setIsRunning] = useState(false);
  const [selectedMap, setSelectedMap] = useState('intersection');
  const [aiEnabled, setAiEnabled] = useState(false);
  const [beforeAiResults, setBeforeAiResults] = useState(null);
  const [afterAiResults, setAfterAiResults] = useState(null);
  const [comparisonResult, setComparisonResult] = useState(null);
  const [isTesting, setIsTesting] = useState(false);

  useEffect(() => {
    if (!isRunning) return;

    const interval = setInterval(() => {
      axios.get('/step')
        .then(response => {
          setSimData(response.data);
        })
        .catch(error => {
          console.error("Error fetching sim step:", error);
          // Stop polling if the simulation is no longer reachable
          setIsRunning(false);
        });
    }, 50); // Step every 0.05 seconds

    return () => clearInterval(interval);
  }, [isRunning]);

  const handleStartSimulation = () => {
    axios.post('/start', { map_name: selectedMap })
      .then(res => {
        alert(res.data.message);
        setIsRunning(true);
        setAiEnabled(false); // Reset AI state on new simulation
      })
      .catch(error => console.error("Error starting simulation:", error));
  };

  const runPerformanceTest = (aiMode) => {
    const run_id = `${selectedMap}_${aiMode ? 'after_ai' : 'before_ai'}`;
    setIsTesting(true);
    setComparisonResult(null); // Clear previous comparison
    if (aiMode) setAfterAiResults(null); else setBeforeAiResults(null);

    alert(`Starting performance test for ${run_id}. The SUMO GUI will launch and run for the full simulation duration. Please wait for it to complete and close automatically.`);
    
    axios.post('/start', { map_name: selectedMap, run_id: run_id, ai_mode: aiMode })
      .then(res => {
        // The backend now directly returns the summary data
        if (aiMode) {
          setAfterAiResults(res.data);
        } else {
          setBeforeAiResults(res.data);
        }
        alert(`Performance run ${run_id} completed and results have been recorded.`);
      })
      .catch(error => {
        alert(error.response?.data?.error || `An error occurred during the ${run_id} run.`);
        console.error(`Error during performance test for ${run_id}:`, error);
      })
      .finally(() => setIsTesting(false));
  };

  const handleComparison = () => {
    if (!beforeAiResults || !afterAiResults) {
      alert("Please run both the baseline and AI simulations before comparing.");
      return;
    }
    setComparisonResult({
      before_ai: beforeAiResults,
      after_ai: afterAiResults
    });
  };

  const handleToggleAI = () => {
    axios.post('/toggle-ai')
      .then(res => {
        alert(res.data.message);
        setAiEnabled(res.data.ai_enabled);
      })
      .catch(error => console.error("Error toggling AI:", error));
  };


  const chartData = [
    { name: 'West-East', vehicles: simData?.vehicles_we || 0 },
    { name: 'North-South', vehicles: simData?.vehicles_ns || 0 }
  ];

  return (
    <div className="App">
      <h1>Smart Traffic Management Dashboard</h1>
      
      <div className="controls">
        <div className="simulation-setup">
          <select onChange={(e) => setSelectedMap(e.target.value)} value={selectedMap} disabled={isRunning}>
            <option value="intersection">Simple Intersection</option>
            <option value="bangalore">Bangalore Silk Junction</option>
          </select>
          <button onClick={handleStartSimulation} disabled={isRunning}>
            Start Simulation
          </button>
        </div>

        <div className="simulation-actions">
          <button onClick={handleToggleAI} disabled={!isRunning}>
            {aiEnabled ? 'Disable AI' : 'Enable AI'}
          </button>
        </div>
      </div>

      {isRunning && (
        <div className="main-content">
        <div className="metrics">
          <h2>Live Traffic Count (Interactive Mode)</h2>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chartData}>
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="vehicles" fill="#8884d8" />
            </BarChart>
          </ResponsiveContainer>
          {simData && simData.current_phase !== undefined && (
            <p>Current Green Light Phase: <strong>{simData.current_phase}</strong></p>
          )}
          {aiEnabled !== null && (
            <p>AI Status: <strong>{aiEnabled ? 'Enabled' : 'Disabled'}</strong></p>
          )}
        </div>
      </div>
      )}

      <div className="performance-test">
        <h2>Performance Test</h2>
        <p>Run simulations in the background to compare performance with and without AI.</p>
        <div className="controls">
          <button onClick={() => runPerformanceTest(false)} disabled={isTesting || isRunning}>
            Run Baseline (No AI)
          </button>
          <button onClick={() => runPerformanceTest(true)} disabled={isTesting || isRunning}>
            Run with AI
          </button>
          <button onClick={handleComparison} disabled={isTesting || isRunning}>
            Compare Results
          </button>
        </div>

        <div className="results-display">
          {beforeAiResults && (
            <div className="results-table">
              <h4>Baseline Run Results</h4>
              <table>
                <thead><tr><th>Metric</th><th>Value</th></tr></thead>
                <tbody>
                  <tr><td>Avg. Travel Time (s)</td><td>{beforeAiResults.avg_travel_time.toFixed(2)}</td></tr>
                  <tr><td>Avg. Waiting Time (s)</td><td>{beforeAiResults.avg_waiting_time.toFixed(2)}</td></tr>
                  <tr><td>Vehicles Completed</td><td>{beforeAiResults.vehicles_completed}</td></tr>
                  <tr><td>Avg. EV Waiting Time (s)</td><td>{beforeAiResults.avg_ev_wait_time.toFixed(2)}</td></tr>
                </tbody>
              </table>
            </div>
          )}
          {afterAiResults && (
            <div className="results-table">
              <h4>AI Run Results</h4>
              <table>
                <thead><tr><th>Metric</th><th>Value</th></tr></thead>
                <tbody>
                  <tr><td>Avg. Travel Time (s)</td><td>{afterAiResults.avg_travel_time.toFixed(2)}</td></tr>
                  <tr><td>Avg. Waiting Time (s)</td><td>{afterAiResults.avg_waiting_time.toFixed(2)}</td></tr>
                  <tr><td>Vehicles Completed</td><td>{afterAiResults.vehicles_completed}</td></tr>
                  <tr><td>Avg. EV Waiting Time (s)</td><td>{afterAiResults.avg_ev_wait_time.toFixed(2)}</td></tr>
                </tbody>
              </table>
            </div>
          )}
        </div>

        {comparisonResult && (
          <div className="results-table comparison">
            <h3>Comparison for '{selectedMap}' Map</h3>
            <table>
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Before AI (Fixed Timer)</th>
                  <th>After AI (Smart System)</th>
                  <th>Improvement</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Avg. Travel Time (s)</td>
                  <td>{comparisonResult.before_ai.avg_travel_time.toFixed(2)}</td>
                  <td>{comparisonResult.after_ai.avg_travel_time.toFixed(2)}</td>
                  <td style={{ color: comparisonResult.after_ai.avg_travel_time < comparisonResult.before_ai.avg_travel_time ? 'green' : 'red' }}>
                    {(((comparisonResult.after_ai.avg_travel_time - comparisonResult.before_ai.avg_travel_time) / comparisonResult.before_ai.avg_travel_time) * 100).toFixed(2)}%
                  </td>
                </tr>
                <tr>
                  <td>Avg. Waiting Time (s)</td>
                  <td>{comparisonResult.before_ai.avg_waiting_time.toFixed(2)}</td>
                  <td>{comparisonResult.after_ai.avg_waiting_time.toFixed(2)}</td>
                  <td style={{ color: comparisonResult.after_ai.avg_waiting_time < comparisonResult.before_ai.avg_waiting_time ? 'green' : 'red' }}>
                    {comparisonResult.before_ai.avg_waiting_time > 0 ? 
                      (((comparisonResult.after_ai.avg_waiting_time - comparisonResult.before_ai.avg_waiting_time) / comparisonResult.before_ai.avg_waiting_time) * 100).toFixed(2) + '%' : 
                      'N/A'
                    }
                  </td>
                </tr>
                <tr>
                  <td>Avg. EV Waiting Time (s)</td>
                  <td>{comparisonResult.before_ai.avg_ev_wait_time.toFixed(2)}</td>
                  <td>{comparisonResult.after_ai.avg_ev_wait_time.toFixed(2)}</td>
                  <td style={{ color: comparisonResult.after_ai.avg_ev_wait_time < comparisonResult.before_ai.avg_ev_wait_time ? 'green' : 'red' }}>
                    {comparisonResult.before_ai.avg_ev_wait_time > 0 ?
                      (((comparisonResult.after_ai.avg_ev_wait_time - comparisonResult.before_ai.avg_ev_wait_time) / comparisonResult.before_ai.avg_ev_wait_time) * 100).toFixed(2) + '%' :
                      'N/A'
                    }
                  </td>
                </tr>
                <tr>
                  <td>Vehicles Completed</td>
                  <td>{comparisonResult.before_ai.vehicles_completed}</td>
                  <td>{comparisonResult.after_ai.vehicles_completed}</td>
                  <td style={{ color: comparisonResult.after_ai.vehicles_completed > comparisonResult.before_ai.vehicles_completed ? 'green' : 'red' }}>
                    {(((comparisonResult.after_ai.vehicles_completed - comparisonResult.before_ai.vehicles_completed) / comparisonResult.before_ai.vehicles_completed) * 100).toFixed(2)}%
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
