import subprocess
import sys
import atexit
import time
import os

# Add SUMO tools to the Python path to ensure the correct traci library is used.
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    # Fallback based on the path from your error logs
    sys.path.append(r"C:\Program Files (x86)\Eclipse\Sumo\tools")

import traci
from flask import Flask, jsonify
from flask_cors import CORS

# --- Flask App Initialization ---
app = Flask(__name__)
CORS(app)

# --- SUMO Configuration ---
traci_port = 8813
MAP_CONFIGS = {
    "intersection": "simulation/intersection.sumocfg",
    "bangalore": "../Banglore_Silk_Junction_Map/osm.sumocfg"
}

# --- Global State ---
sumo_process = None
ai_enabled = False
emergency_vehicle_counter = 0
# State for the adaptive AI controller
tl_state = {
    "J1": {
        "current_phase_index": 0,
        "phase_start_time": 0.0
    }
}

# --- SUMO Simulation Management ---
def apply_adaptive_ai():
    """The adaptive AI logic for the simple intersection map."""
    if "J1" not in traci.trafficlight.getIDList():
        return

    MIN_GREEN_TIME = 10
    MAX_GREEN_TIME = 60
    YELLOW_TIME = 3

    current_time = traci.simulation.getTime()
    state = tl_state["J1"]
    phase_duration = current_time - state["phase_start_time"]
    is_green_phase = state["current_phase_index"] in [0, 2]

    if is_green_phase and phase_duration > MIN_GREEN_TIME:
        if state["current_phase_index"] == 0: # WE Green
            demand_on_green = traci.edge.getLastStepVehicleNumber("WN") + traci.edge.getLastStepVehicleNumber("EN")
            demand_on_red = traci.edge.getLastStepVehicleNumber("NN") + traci.edge.getLastStepVehicleNumber("SN")
        else: # NS Green
            demand_on_green = traci.edge.getLastStepVehicleNumber("NN") + traci.edge.getLastStepVehicleNumber("SN")
            demand_on_red = traci.edge.getLastStepVehicleNumber("WN") + traci.edge.getLastStepVehicleNumber("EN")

        if phase_duration > MAX_GREEN_TIME or (demand_on_green == 0 and demand_on_red > 0):
            next_phase_index = state["current_phase_index"] + 1
            traci.trafficlight.setPhase("J1", next_phase_index)
            state["current_phase_index"] = next_phase_index
            state["phase_start_time"] = current_time
    elif not is_green_phase and phase_duration > YELLOW_TIME:
        next_phase_index = (state["current_phase_index"] + 1) % 4
        traci.trafficlight.setPhase("J1", next_phase_index)
        state["current_phase_index"] = next_phase_index
        state["phase_start_time"] = current_time

def run_performance_simulation(map_name, run_id, ai_mode):
    """Runs a full simulation, waits for it to complete, then parses and returns the results."""
    config_path = MAP_CONFIGS.get(map_name)
    if not config_path:
        raise ValueError("Invalid map name specified")

    summary_file = f"outputs/{run_id}_summary.xml"
    sumo_cmd = ["sumo-gui", "-c", config_path, "--remote-port", str(traci_port), "--start",
                "--tripinfo-output", f"outputs/{run_id}_tripinfo.xml",
                "--summary-output", summary_file]
    
    if not os.path.exists("outputs"): os.makedirs("outputs")
    
    print(f"Starting performance run: {' '.join(sumo_cmd)}")
    sumo_process = subprocess.Popen(sumo_cmd)
    
    try:
        traci.init(traci_port, numRetries=30)
        print("Connected to SUMO for performance run.")
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            if ai_mode:
                apply_adaptive_ai()
        print(f"Performance run {run_id} simulation loop finished.")
    finally:
        if traci.isLoaded(): traci.close()
        print("Waiting for SUMO process to terminate...")
        sumo_process.wait() # Wait for the process to fully close
        print("SUMO process terminated.")
        return parse_summary_robustly(summary_file)

def start_interactive_simulation(map_name):
    """Starts an interactive simulation controlled by the frontend."""
    global sumo_process, ai_enabled
    if sumo_process: close_sumo()

    config_path = MAP_CONFIGS.get(map_name)
    if not config_path: raise ValueError("Invalid map name specified")

    sumo_cmd = ["sumo-gui", "-c", config_path, "--remote-port", str(traci_port), "--start"]
    ai_enabled = False
    
    print(f"Starting interactive simulation: {' '.join(sumo_cmd)}")
    sumo_process = subprocess.Popen(sumo_cmd)
    
    try:
        traci.init(traci_port, numRetries=30)
        print("Successfully connected to SUMO for interactive mode.")
    except traci.TraCIException as e:
        print(f"Could not connect to SUMO: {e}")
        if sumo_process: sumo_process.terminate()
        sys.exit(1)

def close_sumo():
    """Closes the TraCI connection and terminates the SUMO process."""
    if traci.isLoaded():
        traci.close()
        print("TraCI connection closed.")
    if sumo_process:
        sumo_process.terminate()
        print("SUMO process terminated.")

# Register the close_sumo function to be called on script exit
atexit.register(close_sumo)

# --- API Endpoints ---
@app.route('/step', methods=['GET'])
def simulation_step():
    """
    Advances the simulation by one step and applies traffic management logic.
    """
    traci.simulationStep()
    if ai_enabled:
        apply_adaptive_ai()

    # --- Data Collection (example for intersection map) ---
    data = {}
    if "J1" in traci.trafficlight.getIDList():
        data["vehicles_we"] = traci.edge.getLastStepVehicleNumber("WN")
        data["vehicles_ns"] = traci.edge.getLastStepVehicleNumber("NN")
        data["current_phase"] = traci.trafficlight.getPhase("J1")
    
    return jsonify(data)

@app.route('/dispatch-emergency', methods=['POST'])
def dispatch_emergency():
    """
    Dynamically adds a new emergency vehicle to the simulation.
    """
    global emergency_vehicle_counter
    
    if not traci.isLoaded():
        return jsonify({"error": "Simulation not running."}), 400

    # This is a map-specific feature. Check if the required edges exist.
    if "WN" not in traci.edge.getIDList() or "NE" not in traci.edge.getIDList():
        return jsonify({"error": "Emergency dispatch is only configured for the simple intersection map."}), 400

    # Define a simple route for the emergency vehicle for the intersection map
    try:
        traci.route.add("emergency_route_dynamic", ["WN", "NE"])
    except traci.TraCIException:
        # Route already exists, ignore the error
        pass

    vehicle_id = f"emergency_{emergency_vehicle_counter}"
    emergency_vehicle_counter += 1
    
    traci.vehicle.add(
        vehID=vehicle_id,
        routeID="emergency_route_dynamic",
        typeID="emergency_vehicle",
        departLane="free"
    )
    # Allow the vehicle to ignore traffic lights and other constraints
    traci.vehicle.setSpeedMode(vehicle_id, 0)
    
    print(f"Dispatched emergency vehicle: {vehicle_id}")
    return jsonify({"message": f"Dispatched emergency vehicle: {vehicle_id}"})

@app.route('/start', methods=['POST'])
def start_simulation():
    """Starts a new SUMO simulation, either interactive or for performance testing."""
    from flask import request
    map_name = request.json.get('map_name', 'intersection')
    run_id = request.json.get('run_id')
    ai_mode = request.json.get('ai_mode')
    
    try:
        if run_id:
            summary_data = run_performance_simulation(map_name, run_id, ai_mode)
            if "error" in summary_data:
                return jsonify({"error": summary_data["error"]}), 500
            return jsonify(summary_data)
        else:
            start_interactive_simulation(map_name)
            return jsonify({"message": f"Interactive simulation started with {map_name} map."})
    except (ValueError, FileNotFoundError) as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500

@app.route('/toggle-ai', methods=['POST'])
def toggle_ai():
    """Toggles the AI traffic management logic on or off."""
    global ai_enabled
    ai_enabled = not ai_enabled
    status = "enabled" if ai_enabled else "disabled"
    return jsonify({"message": f"AI logic has been {status}.", "ai_enabled": ai_enabled})

import xml.etree.ElementTree as ET

def parse_summary_robustly(file_path):
    """Parses a SUMO summary XML file robustly, handling potential parsing errors."""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        all_steps = root.findall('step')
        if not all_steps:
            return {}
        
        last_step = all_steps[-1]
        return {
            "avg_travel_time": float(last_step.get('meanTravelTime', 0)),
            "avg_waiting_time": float(last_step.get('meanWaitingTime', 0)),
            "vehicles_completed": int(last_step.get('ended', 0)),
        }
    except ET.ParseError as e:
        print(f"XML Parse Error in {file_path}: {e}")
        return {"error": f"XML parsing error: {e}"}
    except FileNotFoundError:
        return {"error": "Summary file not found."}
    except Exception as e:
        print(f"Unexpected error parsing {file_path}: {e}")
        return {"error": f"An unexpected error occurred: {e}"}


# --- Main Execution ---
if __name__ == '__main__':
    # Do not start SUMO automatically anymore. It will be started via the /start endpoint.
    print("Flask server is running. Send a POST request to /start to launch the simulation.")
    app.run(host='0.0.0.0', port=8001)
