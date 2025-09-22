# AI-Powered Smart Traffic Management System

This project is a comprehensive traffic simulation and management system that uses a Python-based AI controller to optimize traffic flow in real-time. It features a React-based web dashboard for visualizing traffic, controlling the simulation, and analyzing performance metrics.

## Features

- **Multiple Map Support:** Simulate traffic on a simple intersection, a complex real-world map of Bangalore's Silk Junction, or a map of Odisha's Rasulgarh Square.
- **Intelligent AI Controller:** A map-agnostic AI that automatically detects and controls all traffic light junctions in any loaded map.
- **Adaptive Traffic Control:** The AI prioritizes traffic flow based on real-time vehicle demand, intelligently extending green light times to clear congestion.
- **Emergency Vehicle Preemption:** The AI detects approaching emergency vehicles and clears a path for them by safely transitioning traffic lights to green in their direction.
- **Performance Analysis:** A built-in testing suite allows you to run back-to-back simulations with and without the AI enabled. The dashboard then displays a detailed comparison of key performance metrics, including:
  - Average Travel Time
  - Average Waiting Time
  - Vehicle Throughput
  - Average Emergency Vehicle Waiting Time
- **Interactive and Performance Modes:** Run simulations in an interactive mode with a GUI for visualization, or in a faster, backend-controlled performance mode to gather metrics.

## Prerequisites

- **SUMO (Simulation of Urban MObility):** Version 1.10.0 or newer. Make sure the `SUMO_HOME` environment variable is set, and that `%SUMO_HOME%\bin` is in your system's PATH.
- **Python:** Version 3.8 or newer.
- **Node.js and npm:** Latest LTS version recommended.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Marvin-Remiigius/AI-Traffic-Management.git
    cd AI-Traffic-Management
    ```

2.  **Install Backend Dependencies:**
    ```bash
    pip install -r backend/requirements.txt
    ```
    *(Note: A `requirements.txt` file will be created in the next step)*

3.  **Install Frontend Dependencies:**
    ```bash
    cd frontend
    npm install
    cd ..
    ```

## How to Run

You will need to run the backend and frontend servers in two separate terminals.

1.  **Start the Backend Server:**
    - Open a terminal in the project's root directory.
    - Navigate to the backend folder: `cd backend`
    - Run the Python server: `python main.py`
    - The server will start and be ready to receive commands from the frontend.

2.  **Start the Frontend Application:**
    - Open a **new** terminal in the project's root directory.
    - Navigate to the frontend folder: `cd frontend`
    - Start the React development server: `npm start`
    - This will automatically open the dashboard in your browser at `http://localhost:3000`.

## How to Use the Dashboard

- **Interactive Simulation:**
  1.  Use the dropdown menu to select a map.
  2.  Click "Start Simulation" to launch the SUMO GUI.
  3.  While the simulation is running, you can click "Enable AI" / "Disable AI" to toggle the smart traffic logic.

- **Performance Testing:**
  1.  Select the map you want to test from the dropdown.
  2.  Click **"Run Baseline (No AI)"**. The SUMO GUI will launch and run to completion. When it closes, a table with the baseline results will appear.
  3.  Click **"Run with AI"**. The SUMO GUI will launch for the AI-controlled run. When it closes, a second table with the AI results will appear.
  4.  Click **"Compare Results"** to see the final comparison table with the percentage improvements.
