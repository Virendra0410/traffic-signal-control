import traci

sumo_cmd = ["sumo-gui", "-c", "osm.sumocfg"]
traci.start(sumo_cmd)

print("Traffic Light IDs:")
print(traci.trafficlight.getIDList())

traci.close()