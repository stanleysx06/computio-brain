from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

app = FastAPI()

# CRITICAL: This allows your public Netlify website to talk to your server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_machines = {}
pending_jobs = set() # Queue for starting jobs
stop_jobs = set()    # Queue for stopping jobs

class MachineStats(BaseModel):
    machine_id: str
    cpu_usage_percent: float
    ram_total_gb: float
    ram_available_gb: float
    gpu_info: str

class RentRequest(BaseModel):
    machine_id: str

@app.post("/heartbeat")
def receive_heartbeat(stats: MachineStats):
    # 1. Update the ledger
    active_machines[stats.machine_id] = stats.model_dump()
    
    # 2. Check the stop queue FIRST to prioritize shutting down
    if stats.machine_id in stop_jobs:
        stop_jobs.remove(stats.machine_id)
        return {"status": "success", "command": "stop-job"}
        
    # 3. Check the start queue: Did a renter book this specific machine?
    if stats.machine_id in pending_jobs:
        pending_jobs.remove(stats.machine_id)
        return {"status": "success", "command": "start-job"} # Tell the agent to boot Docker!
        
    return {"status": "success", "command": "idle"}

@app.get("/marketplace")
def get_marketplace():
    return {"available_compute": active_machines}

@app.post("/rent")
def rent_machine(req: RentRequest):
    if req.machine_id in active_machines:
        # We put the job in the queue, waiting for the Agent's next heartbeat
        pending_jobs.add(req.machine_id)
        return {"status": "success", "message": "Rental secured! Agent is booting the room."}
    return {"status": "error", "message": "Machine is currently offline."}

@app.post("/stop")
def stop_machine(req: RentRequest):
    if req.machine_id in active_machines:
        # Put the stop order in the queue
        stop_jobs.add(req.machine_id)
        return {"status": "success", "message": "Stop signal sent to Agent!"}
    return {"status": "error", "message": "Machine is currently offline."}

@app.post("/offline")
def offline_machine(req: RentRequest):
    # If the provider app hits "Stop", erase them from the active ledger
    if req.machine_id in active_machines:
        del active_machines[req.machine_id]
        return {"status": "success", "message": "Machine removed from marketplace."}
    return {"status": "success", "message": "Machine already offline."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)