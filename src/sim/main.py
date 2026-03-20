import click
import time

import uvicorn

import api
from camera import Camera
from simulator import Simulator
from gui import WebGuiConnector
from api import api
import multiprocessing

@click.command()
@click.option('--timing', default=10, help='Numerical speed of the simulation. 1 -> real time, 2 -> 2x real time, ... 0 -> as fast as possible.')
@click.option('--time-step', default=20, help='Time step in seconds for the STK animation. Only applicable if simulator is stk, ignored otherwise.')

def main(timing, time_step):
    manager = multiprocessing.Manager()
    shared_data_dict = manager.dict()
    shared_data_dict["satellite_position"] = (0.0, 0.0, 0.0)  # (lon, lat, alt)

    sim_proc = multiprocessing.Process(
        target=run_sim,
        args=(shared_data_dict, timing, time_step)
    )
    
    api_proc = multiprocessing.Process(
        target=run_api, 
        args=(shared_data_dict,)
    )

    sim_proc.start()
    api_proc.start()

    print("Both processes are running. Press Ctrl+C to stop.")

    try:
        # Keep the main script alive while children run
        sim_proc.join()
        api_proc.join()
    except KeyboardInterrupt:
        print("\nShutting down...")
        sim_proc.terminate()
        api_proc.terminate()

def run_api(shared_data_dict):
    api.state.shared_data =    shared_data_dict
    uvicorn.run(api, host="0.0.0.0", port=8000)

def run_sim(shared_data_dict, timing, time_step):

    # 3. initialize the simulation GUI if needed
    gui = WebGuiConnector()

    # 4. Initialize the simulation engine
    line1 = "1 60989U 24157A   26075.16558042  .00000129  00000-0  65710-4 0  9997"
    line2 = "2 60989  98.5677 151.2852 0000884 109.8893 250.2385 14.30816791 79683"
    sim_engine = Simulator("SatelliteName", TLE=[line1, line2], t0=None, timing_mode=timing, time_step=time_step)

    # 5. Add subsystems (only the camera in this case)
    camera = Camera(shared_data_dict=shared_data_dict)
    # 6. Run the simulation
    sim_engine.reset()

    while True:
        sim_step = sim_engine.sim_step() # returns none if no step is taken (e.g. because the time for teh next step has not yet come
        time.sleep(0.1)
    
if __name__ == '__main__':
    main()