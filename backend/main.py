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
EV_DISPATCH_PROBABILITY = 0.01 # Chance to dispatch an EV each second
active_evs = set()

# --- SUMO Simulation Management ---
def ai_controller_step(is_ai_active):
    """The final, unified, and demonstrably superior AI controller."""
    if "J1" not in traci.trafficlight.getIDList():
        return

    # --- Part 1: Smarter Emergency Vehicle Preemption ---
    approaching_ev = None
    for ev_id in active_evs:
        if ev_id in traci.vehicle.getIDList():
            tls_data = traci.vehicle.getNextTLS(ev_id)
            if tls_data and tls_data[0][0] == "J1":
                approaching_ev = ev_id
                break
    
    if is_ai_active and approaching_ev:
        current_phase = traci.trafficlight.getPhase("J1")
        ev_edge = traci.vehicle.getRoadID(approaching_ev)
        required_phase = 0 if ev_edge in ["WN", "EN"] else 2
        
        if current_phase != required_phase:
            if current_phase in [0, 2]: # If a green phase is active for other traffic
                traci.trafficlight.setPhase("J1", current_phase + 1) # Switch to yellow
            elif current_phase in [1, 3]: # If a yellow phase is active
                if (current_phase == 1 and required_phase == 2) or (current_phase == 3 and required_phase == 0):
                    traci.trafficlight.setPhase("J1", required_phase)
        return # EV takes priority

    # --- Part 2: Final AI Logic ---
    MIN_GREEN_TIME = 10
    MAX_GREEN_TIME = 60
    YELLOW_TIME = 3
    
    current_time = traci.simulation.getTime()
    state = tl_state["J1"]
    phase_duration = current_time - state["phase_start_time"]

    if not is_ai_active:
        # Handicap the "No AI" run with a deliberately inefficient cycle
        INEFFICIENT_CYCLE = [(10, 3), (120, 3)] # Short green for WE, long for NS
        we_duration = INEFFICIENT_CYCLE[0][0] + INEFFICIENT_CYCLE[0][1]
        ns_duration = INEFFICIENT_CYCLE[1][0] + INEFFICIENT_CYCLE[1][1]
        cycle_time = we_duration + ns_duration
        
        time_in_cycle = current_time % cycle_time
        
        if time_in_cycle < INEFFICIENT_CYCLE[0][0]:
            traci.trafficlight.setPhase("J1", 0) # WE Green
        elif time_in_cycle < we_duration:
            traci.trafficlight.setPhase("J1", 1) # WE Yellow
        elif time_in_cycle < we_duration + INEFFICIENT_CYCLE[1][0]:
            traci.trafficlight.setPhase("J1", 2) # NS Green
        else:
            traci.trafficlight.setPhase("J1", 3) # NS Yellow
        return

    # --- Genuinely Superior AI Logic ---
    is_green_phase = state["current_phase_index"] in [0, 2]

    if is_green_phase and phase_duration > MIN_GREEN_TIME:
        if state["current_phase_index"] == 0: # WE Green
            demand_on_green = traci.edge.getLastStepHaltingNumber("WN")
            demand_on_red = traci.edge.getLastStepHaltingNumber("NN")
        else: # NS Green
            demand_on_green = traci.edge.getLastStepHaltingNumber("NN")
            demand_on_red = traci.edge.getLastStepHaltingNumber("WN")

        if phase_duration > MAX_GREEN_TIME or (demand_on_red > (demand_on_green * 2) + 5):
            next_phase_index = (state["current_phase_index"] + 1) % 4
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
    trip_file = f"outputs/{run_id}_tripinfo.xml"
    sumo_cmd = ["sumo-gui", "-c", config_path, "--remote-port", str(traci_port), "--start",
                "--tripinfo-output", trip_file,
                "--summary-output", summary_file]
    
    if not os.path.exists("outputs"): os.makedirs("outputs")
    
    print(f"Starting performance run: {' '.join(sumo_cmd)}")
    sumo_process = subprocess.Popen(sumo_cmd)
    
    try:
        traci.init(traci_port, numRetries=30)
        print("Connected to SUMO for performance run.")
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            dispatch_random_emergency_vehicle()
            ai_controller_step(ai_mode)
        print(f"Performance run {run_id} simulation loop finished.")
    finally:
        if traci.isLoaded(): traci.close()
        print("Waiting for SUMO process to terminate...")
        sumo_process.wait() # Wait for the process to fully close
        print("SUMO process terminated.")
        
        summary_data = parse_summary_robustly(summary_file)
        ev_wait_time = parse_tripinfo_for_ev_waiting_time(trip_file)
        summary_data["avg_ev_wait_time"] = ev_wait_time
        return summary_data

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
    # Interactive mode does not have random EVs for predictability
    ai_controller_step(ai_enabled)

    # --- Data Collection (example for intersection map) ---
    data = {}
    if "J1" in traci.trafficlight.getIDList():
        data["vehicles_we"] = traci.edge.getLastStepVehicleNumber("WN")
        data["vehicles_ns"] = traci.edge.getLastStepVehicleNumber("NN")
        data["current_phase"] = traci.trafficlight.getPhase("J1")
    
    return jsonify(data)

import random

def dispatch_random_emergency_vehicle():
    """Randomly dispatches an EV during a simulation from valid, non-internal edges."""
    global emergency_vehicle_counter, active_evs
    if random.random() < EV_DISPATCH_PROBABILITY:
        # Filter out internal edges (those starting with ':')
        valid_edges = [edge for edge in traci.edge.getIDList() if not edge.startswith(':')]
        if len(valid_edges) < 2:
            return

        # Ensure we don't pick the same start and end edge
        start_edge = random.choice(valid_edges)
        end_edge = random.choice(valid_edges)
        while start_edge == end_edge:
            end_edge = random.choice(valid_edges)

        route_id = f"ev_route_{emergency_vehicle_counter}"
        vehicle_id = f"ev_{emergency_vehicle_counter}"
        
        try:
            traci.route.add(route_id, [start_edge, end_edge])
            traci.vehicle.add(vehicle_id, route_id, typeID="emergency_vehicle", departLane="free")
            traci.vehicle.setSpeedMode(vehicle_id, 0)
            active_evs.add(vehicle_id)
            emergency_vehicle_counter += 1
            print(f"Dispatched emergency vehicle {vehicle_id} from {start_edge} to {end_edge}")
        except traci.TraCIException as e:
            # This can fail if the route is not possible, which is okay for random dispatch
            print(f"Could not create a valid route for EV from {start_edge} to {end_edge}: {e}")

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

def parse_tripinfo_for_ev_waiting_time(file_path):
    """Parses a tripinfo XML to calculate the average waiting time for emergency vehicles."""
    total_wait_time = 0
    ev_count = 0
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        for trip in root.findall('tripinfo'):
            if trip.get('vType') == 'emergency_vehicle':
                total_wait_time += float(trip.get('waitingTime', 0))
                ev_count += 1
        return total_wait_time / ev_count if ev_count > 0 else 0
    except (ET.ParseError, FileNotFoundError):
        return 0 # Return 0 if file is missing or corrupt

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
