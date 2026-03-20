
import datetime
import requests

from pydispatch import dispatcher

TOPIC_SIMULATION_COMMAND = "simulation.command"
TOPIC_SATELLITE_GROUND_POSITION = "satellite.ground_position"
TOPIC_SIMULATION_STEP_FORWARD = "simulation.step_forward"
TOPIC_SIMULATION_TICK = "simulation.tick"


import os

BASE_URL = os.environ.get("DASHBOARD_URL", "http://dashboard:8000")


class WebGuiConnector:
    def __init__(self):
        # register all the subscriber callbacks
        dispatcher.connect(self.on_satellite_ground_position, signal=TOPIC_SATELLITE_GROUND_POSITION)
        dispatcher.connect(self.on_sim_tick, signal=TOPIC_SIMULATION_TICK)
        self.sim_status = None

    def on_satellite_ground_position(self, sender, data, time):
        # extract the data
        lon = data.get('lon', 0.0)
        lat = data.get('lat', 0.0)
        alt = data.get('alt', 0.0)

        self.send_telemetry(lat, lon, alt, time)


    def on_sim_tick(self, sender, data):
        json = self.fetch_commands()
        commands = json.get('commands', [])
        if len(commands) > 0:
            for command in commands:
                self.handle_commands(command['command'], command['parameters'])

    def handle_commands(self, command: str, parameters: dict):
        # check if there's a status in the command
        if command == 'start':
            self.start_simulation(parameters)
        elif command == 'pause':
            self.pause_simulation(parameters)
        elif command == 'stop':
            self.reset_simulation(parameters)
        elif command == 'set_start_time':
            self.set_start_time(parameters)
        
        

    def send_telemetry(self, lat, lon, alt_km, time ):
        url = f"{BASE_URL}/api/telemetry/"
        print(f"time: {time}, lat: {lat}, lon: {lon}, alt_km: {alt_km}")
        payload = {
            "satellite": "Test",
            "timestamp": time,
            "latitude": lat,
            "longitude": lon,
            "altitude": alt_km
        }

        try:
            resp = requests.post(url, json=payload, timeout=2)
            resp.raise_for_status()
        except Exception as e:
            print(f"Error sending telemetry: {e}")
        else:
            # Optionally inspect the response
            data = resp.json()
            print(data)
            
        # TODO: send data to the web gui via the api

    def fetch_commands(self) -> dict:
        url = f"{BASE_URL}/api/commands/"
        try:
            resp = requests.get(url, timeout=2)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"Error fetching commands: {e}")
            return {"message": "error", "details": str(e)}
        return resp.json()
    

    def start_simulation(self, parameters):
        print("Starting simulation...")
        dispatcher.send(
            signal=TOPIC_SIMULATION_COMMAND,
            sender=self,
            data={'command': 'start', 'parameters': parameters},
        )


    def pause_simulation(self, parameters):
        print("Pausing simulation...")
        dispatcher.send(
            signal=TOPIC_SIMULATION_COMMAND,
            sender=self,
            data={'command': 'pause', 'parameters': parameters},
        )

    def reset_simulation(self, parameters):
        print("Resetting simulation...")
        dispatcher.send(
            signal=TOPIC_SIMULATION_COMMAND,
            sender=self,
            data={'command': 'reset'},
        )

    def set_start_time(self, parameters):
        print("Setting simulation start time...")
        dispatcher.send(
            signal=TOPIC_SIMULATION_COMMAND,
            sender=self,
            data={'command': 'set_start_time', 'parameters': parameters},
        )
