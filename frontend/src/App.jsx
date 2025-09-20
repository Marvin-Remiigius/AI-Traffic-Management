import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import './App.css';

function App() {
  const [simData, setSimData] = useState(null);
  const [isRunning, setIsRunning] = useState(false);

  useEffect(() => {
    if (!isRunning) return;

    const interval = setInterval(() => {
      axios.get('http://localhost:8000/step')
        .then(response => {
          setSimData(response.data);
        })
        .catch(error => console.error("Error fetching sim step:", error));
    }, 1000); // Step every 1 second

    return () => clearInterval(interval);
  }, [isRunning]);

  const handleEmergency = () => {
    axios.post('http://localhost:8000/emergency')
      .then(res => alert(res.data.message))
      .catch(error => console.error("Error triggering emergency:", error));
  };

  const chartData = [
    { name: 'West-East', vehicles: simData?.vehicles_we || 0 },
    { name: 'North-South', vehicles: simData?.vehicles_ns || 0 }
  ];

  return (
    <div className="App">
      <h1>Smart Traffic Management Dashboard</h1>
      <div className="controls">
        <button onClick={() => setIsRunning(!isRunning)}>
          {isRunning ? 'Stop Simulation' : 'Start Simulation'}
        </button>
        <button onClick={handleEmergency} className="emergency-button">
          Dispatch Emergency Vehicle
        </button>
      </div>

      <div className="main-content">
        <div className="metrics">
          <h2>Live Traffic Count</h2>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chartData}>
              <XAxis dataKey="name" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="vehicles" fill="#8884d8" />
            </BarChart>
          </ResponsiveContainer>
          {simData && (
            <p>Current Green Light Phase: <strong>{simData.current_phase}</strong></p>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
