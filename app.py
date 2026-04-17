from flask import Flask, render_template, request, jsonify
import traci
import time

app = Flask(__name__)

SUMO_BINARY = "sumo-gui"
MAX_STEPS = 500

# ================= CONFIG =================
GRID_CONFIG = {
    "1x1": {
        "cfg": "sumo_files/1x1/1x1.sumocfg",
        "tls_ids": ["t"]
    },
    "3x3": {
        "cfg": "sumo_files/3x3/3x3.sumocfg",
        "tls_ids": ['0','1','2','3','4','5','6','7','8']
    },
    "4x4": {
        "cfg": "sumo_files/4x4/4x4.sumocfg",
        "tls_ids": [str(i) for i in range(16)]
    },
    "real": {
        "cfg": "sumo_files/real_map/osm.sumocfg",
        "tls_ids": None
    }
}

# ================= WAIT =================
def get_wait():
    vehicles = traci.vehicle.getIDList()
    if vehicles:
        return sum(traci.vehicle.getWaitingTime(v) for v in vehicles) / len(vehicles)
    return 0


# ================= FIXED =================
def run_fixed(cfg, tls_ids):

    print("\n=== FIXED START ===")

    traci.start([SUMO_BINARY, "-c", cfg])

    if tls_ids is None:
        tls_ids = traci.trafficlight.getIDList()

    log = []

    for step in range(MAX_STEPS):
        traci.simulationStep()

        phase = 0 if (step // 30) % 2 == 0 else 2

        for tls in tls_ids:
            try:
                traci.trafficlight.setPhase(tls, phase)
            except:
                pass

        log.append(get_wait())

        time.sleep(0.08)   #  visible speed

    print("=== FIXED END ===")
    time.sleep(2)          #  keep GUI visible
    traci.close()
    time.sleep(2)          #  gap

    return log


# ================= MULTI GRID =================
def control_grid(tls, tls_ids, last_switch, step, queues):

    q_ns, q_ew = queues[tls]

    neighbors = [n for n in tls_ids if n != tls]
    neighbor_q = sum(sum(queues[n]) for n in neighbors) / len(neighbors) if neighbors else 0

    if step - last_switch[tls] > 15:

        score_ns = q_ns + 0.05 * neighbor_q
        score_ew = q_ew + 0.05 * neighbor_q

        if score_ns > score_ew + 3:
            traci.trafficlight.setPhase(tls, 0)
            last_switch[tls] = step

        elif score_ew > score_ns + 3:
            traci.trafficlight.setPhase(tls, 2)
            last_switch[tls] = step


# ================= MULTI REAL =================
def control_real(tls, last_switch, step):

    if step - last_switch[tls] < 15:
        return

    try:
        logic = traci.trafficlight.getAllProgramLogics(tls)[0]
    except:
        return

    phases = logic.phases
    lanes = traci.trafficlight.getControlledLanes(tls)

    best_phase = None
    best_score = -999999

    for i, p in enumerate(phases):

        if 'g' not in p.state.lower():
            continue

        pressure = 0

        for lane in lanes:
            try:
                incoming = traci.lane.getLastStepVehicleNumber(lane)

                outgoing = 0
                for link in traci.lane.getLinks(lane):
                    if link:
                        outgoing += traci.lane.getLastStepVehicleNumber(link[0])

                pressure += (incoming - outgoing)

            except:
                pass

        if pressure > best_score:
            best_score = pressure
            best_phase = i

    if best_phase is not None:
        traci.trafficlight.setPhase(tls, best_phase)
        last_switch[tls] = step


# ================= MULTI =================
def run_multi(cfg, tls_ids, grid_type):

    print("\n=== MULTI START ===")

    traci.start([SUMO_BINARY, "-c", cfg])

    if tls_ids is None:
        tls_ids = traci.trafficlight.getIDList()

    last_switch = {tls: 0 for tls in tls_ids}
    log = []

    for step in range(MAX_STEPS):
        traci.simulationStep()

        if grid_type != "real":

            queues = {}

            for tls in tls_ids:
                lanes = traci.trafficlight.getControlledLanes(tls)

                mid = len(lanes)//2
                q_ns = sum(traci.lane.getLastStepVehicleNumber(l) for l in lanes[:mid])
                q_ew = sum(traci.lane.getLastStepVehicleNumber(l) for l in lanes[mid:])

                queues[tls] = (q_ns, q_ew)

            for tls in tls_ids:
                control_grid(tls, tls_ids, last_switch, step, queues)

        else:
            for tls in tls_ids:
                control_real(tls, last_switch, step)

        log.append(get_wait())
        time.sleep(0.08)

    print("=== MULTI END ===")
    time.sleep(2)
    traci.close()

    return log


# ================= PIPELINE =================
@app.route("/run", methods=["POST"])
def run_all():

    grid = request.json["grid"]

    cfg = GRID_CONFIG[grid]["cfg"]
    tls_ids = GRID_CONFIG[grid]["tls_ids"]

    # sequential execution
    fixed = run_fixed(cfg, tls_ids)
    multi = run_multi(cfg, tls_ids, grid)

    return jsonify({
        "fixed": fixed,
        "multi": multi
    })


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)