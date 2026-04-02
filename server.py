from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
import time

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
    machine_data = stats.model_dump()
    machine_data["last_seen"] = time.time()
    
    # CRITICAL: Preserve the rental state so the Mac's heartbeats don't overwrite it!
    if stats.machine_id in active_machines:
        machine_data["is_rented"] = active_machines[stats.machine_id].get("is_rented", False)
    else:
        machine_data["is_rented"] = False
        
    active_machines[stats.machine_id] = machine_data
    
    if stats.machine_id in stop_jobs:
        stop_jobs.remove(stats.machine_id)
        return {"status": "success", "command": "stop-job"}
        
    if stats.machine_id in pending_jobs:
        pending_jobs.remove(stats.machine_id)
        return {"status": "success", "command": "start-job"}
        
    return {"status": "success", "command": "idle"}

@app.get("/marketplace")
def get_marketplace():
    current_time = time.time()
    stale_machines = []
    
    for m_id, data in active_machines.items():
        if current_time - data.get("last_seen", current_time) > 15:
            stale_machines.append(m_id)
            
    for m_id in stale_machines:
        del active_machines[m_id]
        if m_id in pending_jobs: pending_jobs.remove(m_id)
        if m_id in stop_jobs: stop_jobs.remove(m_id)

    return {"available_compute": active_machines}

@app.post("/rent")
def rent_machine(req: RentRequest):
    if req.machine_id in active_machines:
        # NEW: The Double-Booking Blocker!
        if active_machines[req.machine_id].get("is_rented"):
            return {"status": "error", "message": "Machine is already in use."}
            
        active_machines[req.machine_id]["is_rented"] = True
        pending_jobs.add(req.machine_id)
        return {"status": "success", "message": "Rental secured!"}
    return {"status": "error", "message": "Machine is offline."}

@app.post("/stop")
def stop_machine(req: RentRequest):
    if req.machine_id in active_machines:
        # NEW: Mark the machine as available again for the next person
        active_machines[req.machine_id]["is_rented"] = False
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