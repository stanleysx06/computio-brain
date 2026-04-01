from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
import time  # NEW: We need this to track timestamps!

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_machines = {}
pending_jobs = set()
stop_jobs = set()

class MachineStats(BaseModel):
    machine_id: str
    cpu_usage_percent: float
    ram_total_gb: float
    ram_available_gb: float
    gpu_info: str
    workspace_url: Optional[str] = None

class RentRequest(BaseModel):
    machine_id: str

@app.post("/heartbeat")
def receive_heartbeat(stats: MachineStats):
    # 1. Update the ledger WITH a timestamp
    machine_data = stats.model_dump()
    machine_data["last_seen"] = time.time()
    active_machines[stats.machine_id] = machine_data
    
    # 2. Check the stop queue
    if stats.machine_id in stop_jobs:
        stop_jobs.remove(stats.machine_id)
        return {"status": "success", "command": "stop-job"}
        
    # 3. Check the start queue
    if stats.machine_id in pending_jobs:
        pending_jobs.remove(stats.machine_id)
        return {"status": "success", "command": "start-job"}
        
    return {"status": "success", "command": "idle"}

@app.get("/marketplace")
def get_marketplace():
    # NEW: The Garbage Collector!
    current_time = time.time()
    stale_machines = []
    
    # Scan for any machines that haven't sent a heartbeat in 15 seconds
    for m_id, data in active_machines.items():
        if current_time - data.get("last_seen", current_time) > 15:
            stale_machines.append(m_id)
            
    # Kick the dead machines off the network
    for m_id in stale_machines:
        del active_machines[m_id]
        if m_id in pending_jobs: pending_jobs.remove(m_id)
        if m_id in stop_jobs: stop_jobs.remove(m_id)

    return {"available_compute": active_machines}

@app.post("/rent")
def rent_machine(req: RentRequest):
    if req.machine_id in active_machines:
        pending_jobs.add(req.machine_id)
        return {"status": "success", "message": "Rental secured!"}
    return {"status": "error", "message": "Machine is offline."}

@app.post("/stop")
def stop_machine(req: RentRequest):
    if req.machine_id in active_machines:
        stop_jobs.add(req.machine_id)
        return {"status": "success", "message": "Stop signal sent!"}
    return {"status": "error", "message": "Machine is offline."}

@app.post("/offline")
def offline_machine(req: RentRequest):
    if req.machine_id in active_machines:
        del active_machines[req.machine_id]
        return {"status": "success", "message": "Removed."}
    return {"status": "success", "message": "Already offline."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)