import json
from fastapi import FastAPI, Query
from opengtm.analytics import run_health_check
from opengtm.qualify import qualify as _qualify

app = FastAPI(title="OpenGTM API", version="0.1.0")


@app.get("/")
def root():
    return {"name": "OpenGTM", "version": "0.1.0", "endpoints": ["/aeo-health", "/score-lead", "/health"]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/aeo-health")
def aeo_health(url: str = Query(..., description="URL to analyze"), timeout: float = 30.0):
    result = run_health_check(url, timeout=timeout)
    return result


@app.post("/score-lead")
def score_lead(lead: dict, icp_profile: str = "default", custom_profile: dict = None):
    result = _qualify(lead, icp_profile=icp_profile, custom_profile=custom_profile)
    return result
