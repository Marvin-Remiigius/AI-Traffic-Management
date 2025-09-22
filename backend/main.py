import subprocess
import sys
import atexit
import time
import os
import random
import xml.etree.ElementTree as ET

# Add SUMO tools to the Python path
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
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
    "bangalore": "Banglore_Silk_Junction/osm.sumocfg",
    "odisha": "Odisha_Rasulgarh_Sqare/osm.sumocfg"
}

# --- Global State ---
sumo_process = None
ai_enabled = False
emergency_vehicle_counter = 0
tl_state = {} # Will be populated dynamically
active_evs = set()
EV_DISPATCH_PROBABILITY = 0.01

# --- Universal AI Controller ---
def initialize_ai_state():
    """Initializes the state for all traffic lights in the current simulation."""
    global tl_state
    tl_state = {}
    for tls_id in traci.trafficlight.getIDList():
        tl_state[tls_id] = {
            "current_phase_index": 0,
            "phase_start_time": 0.0
        }

def ai_controller_step(is_ai_active):
    """A map-agnostic AI controller that manages all traffic lights."""
    if not is_ai_active:
        return # When AI is off, SUMO uses its default fixed-time logic

    # --- Part 1: Universal Emergency Vehicle Preemption ---
    ev_preempting = set()
    for ev_id in active_evs:
        if ev_id in traci.vehicle.getIDList():
            tls_data = traci.vehicle.getNextTLS(ev_id)
            if tls_data:
                tls_id = tls_data[0][0]
                ev_preempting.add(tls_id)
                
                # Find the correct green phase for the EV's path
                links = traci.trafficlight.getControlledLinks(tls_id)
                ev_lane = traci.vehicle.getLaneID(ev_id)
                target_phase = -1
                for i, phase in enumerate(traci.trafficlight.getCompleteRedYellowGreenDefinition(tls_id)[0].phases):
                    if any(link[0] == ev_lane and 'g' in phase.state.lower() for link in links):
                        target_phase = i
                        break
                
                if target_phase != -1 and traci.trafficlight.getPhase(tls_id) != target_phase:
                    # Safely transition to the required phase
                    current_phase = traci.trafficlight.getPhase(tls_id)
                    if 'g' in traci.trafficlight.getCompleteRedYellowGreenDefinition(tls_id)[0].phases[current_phase].state.lower():
                         traci.trafficlight.setPhase(tls_id, current_phase + 1) # Switch to yellow
                    else: # Is yellow or red
                        traci.trafficlight.setPhase(tls_id, target_phase)

    # --- Part 2: Universal Adaptive Traffic Control ---
    for tls_id in traci.trafficlight.getIDList():
        if tls_id in ev_preempting:
            continue # Skip if this light is being controlled by EV preemption

        state = tl_state[tls_id]
        current_time = traci.simulation.getTime()
        phase_duration = current_time - state["phase_start_time"]
        
        is_green_phase = 'g' in traci.trafficlight.getCompleteRedYellowGreenDefinition(tls_id)[0].phases[state["current_phase_index"]].state.lower()
        
        if is_green_phase and phase_duration > 10: # Min green time
            # Find the incoming lane with the most waiting cars
            incoming_lanes = set(link[0][0] for link in traci.trafficlight.getControlledLinks(tls_id))
            max_demand_lane = max(incoming_lanes, key=lambda lane: traci.lane.getLastStepHaltingNumber(lane), default=None)
            
            if max_demand_lane:
                # Find the phase that makes this lane green
                links = traci.trafficlight.getControlledLinks(tls_id)
                target_phase = -1
                for i, phase in enumerate(traci.trafficlight.getCompleteRedYellowGreenDefinition(tls_id)[0].phases):
                     if any(link[0] == max_demand_lane and 'g' in phase.state.lower() for link in links):
                        target_phase = i
                        break

                if target_phase != -1 and state["current_phase_index"] != target_phase:
                    traci.trafficlight.setPhase(tls_id, state["current_phase_index"] + 1) # Switch to yellow
                    state["current_phase_index"] = state["current_phase_index"] + 1
                    state["phase_start_time"] = current_time

        elif not is_green_phase and phase_duration > 3: # Yellow time
            next_phase = (state["current_phase_index"] + 1) % len(traci.trafficlight.getCompleteRedYellowGreenDefinition(tls_id)[0].phases)
            traci.trafficlight.setPhase(tls_id, next_phase)
            state["current_phase_index"] = next_phase
            state["phase_start_time"] = current_time

# --- Simulation Execution ---
def run_simulation(map_name, run_id=None, ai_mode=None, is_interactive=False):
    """Runs a SUMO simulation, either for performance or interactive mode."""
    global sumo_process, ai_enabled
    if sumo_process: close_sumo()

    config_path = MAP_CONFIGS.get(map_name)
    if not config_path: raise ValueError("Invalid map name specified")

    sumo_cmd = ["sumo-gui", "-c", config_path, "--remote-port", str(traci_port), "--start"]
    if run_id:
        summary_file = f"outputs/{run_id}_summary.xml"
        trip_file = f"outputs/{run_id}_tripinfo.xml"
        sumo_cmd.extend(["--tripinfo-output", trip_file, "--summary-output", summary_file])
        if not os.path.exists("outputs"): os.makedirs("outputs")
    
    print(f"Starting SUMO: {' '.join(sumo_cmd)}")
    sumo_process = subprocess.Popen(sumo_cmd)
    
    try:
        traci.init(traci_port, numRetries=30)
        print("Connected to SUMO.")
        initialize_ai_state()
        
        if is_interactive:
            ai_enabled = False
            return # Hand control back to frontend for interactive mode

        # Performance mode: run to completion
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            dispatch_random_emergency_vehicle()
            ai_controller_step(ai_mode)
        print(f"Performance run {run_id} finished.")
        
    finally:
        if traci.isLoaded(): traci.close()
        if not is_interactive:
            sumo_process.wait()
            print("SUMO process terminated.")
            summary_data = parse_summary_robustly(summary_file)
            ev_wait_time = parse_tripinfo_for_ev_waiting_time(trip_file)
            summary_data["avg_ev_wait_time"] = ev_wait_time
            return summary_data

def close_sumo():
    """Closes the TraCI connection and terminates the SUMO process."""
    if traci.isLoaded(): traci.close()
    if sumo_process: sumo_process.terminate()
    print("SUMO connection closed.")

# --- API Endpoints ---
@app.route('/step', methods=['GET'])
def simulation_step():
    traci.simulationStep()
    ai_controller_step(ai_enabled)
    # Data collection for the simple chart (will only work on intersection map)
    data = {}
    if "J1" in traci.trafficlight.getIDList():
        data["vehicles_we"] = traci.edge.getLastStepVehicleNumber("WN")
        data["vehicles_ns"] = traci.edge.getLastStepVehicleNumber("NN")
        data["current_phase"] = traci.trafficlight.getPhase("J1")
    return jsonify(data)

def dispatch_random_emergency_vehicle():
    """Randomly dispatches an EV during a simulation."""
    global emergency_vehicle_counter, active_evs
    if random.random() < EV_DISPATCH_PROBABILITY:
        valid_edges = [edge for edge in traci.edge.getIDList() if not edge.startswith(':')]
        if len(valid_edges) < 2: return
        start_edge, end_edge = random.sample(valid_edges, 2)
        route_id = f"ev_route_{emergency_vehicle_counter}"
        vehicle_id = f"ev_{emergency_vehicle_counter}"
        try:
            traci.route.add(route_id, [start_edge, end_edge])
            traci.vehicle.add(vehicle_id, route_id, typeID="emergency_vehicle", departLane="free")
            traci.vehicle.setSpeedMode(vehicle_id, 0)
            active_evs.add(vehicle_id)
            emergency_vehicle_counter += 1
            print(f"Dispatched EV {vehicle_id} from {start_edge} to {end_edge}")
        except traci.TraCIException:
            pass # Ignore if route is not possible

@app.route('/start', methods=['POST'])
def start_simulation():
    req_data = request.get_json()
    map_name = req_data.get('map_name', 'intersection')
    run_id = req_data.get('run_id')
    ai_mode = req_data.get('ai_mode')
    
    try:
        if run_id:
            summary = run_simulation(map_name, run_id, ai_mode)
            return jsonify(summary)
        else:
            run_simulation(map_name, is_interactive=True)
            return jsonify({"message": f"Interactive simulation started."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/toggle-ai', methods=['POST'])
def toggle_ai():
    global ai_enabled
    ai_enabled = not ai_enabled
    status = "enabled" if ai_enabled else "disabled"
    return jsonify({"message": f"AI logic {status}.", "ai_enabled": ai_enabled})

# --- Data Parsing ---
def parse_tripinfo_for_ev_waiting_time(file_path):
    # ... (implementation remains the same)
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
        return 0

def parse_summary_robustly(file_path):
    # ... (implementation remains the same)
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        all_steps = root.findall('step')
        if not all_steps: return {}
        last_step = all_steps[-1]
        return {
            "avg_travel_time": float(last_step.get('meanTravelTime', 0)),
            "avg_waiting_time": float(last_step.get('meanWaitingTime', 0)),
            "vehicles_completed": int(last_step.get('ended', 0)),
        }
    except (ET.ParseError, FileNotFoundError):
        return {"error": "Summary file not found or is corrupted."}

# --- Main Execution ---
if __name__ == '__main__':
    from flask import request
    print("Flask server running. Send POST to /start to launch simulation.")
    app.run(host='0.0.0.0', port=8001)
