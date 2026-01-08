from datetime import datetime

def handle_roi_scan(job: dict, needs: dict):
    return {
        "job_id": job.get("job_id", "unknown"),
        "status": "SUCCESS",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "roi_plan": {
            "focus": "API resale / AI-funksjoner for små SaaS",
            "ideas": [
                "White-label AI API for små SaaS (chat, analyse, support)",
                "API-pakker per måned (starter / pro / agency)",
                "Cold outreach mot SaaS founders på LinkedIn + e-post"
            ],
            "pricing_example": {
                "starter": "€49 / mnd",
                "pro": "€149 / mnd",
                "agency": "€399 / mnd"
            },
            "next_steps": [
                "Velg 1 konkret API-usecase",
                "Sett opp enkel landingsside",
                "Start manuell outreach (20–30 kontakter)"
            ]
        }
    }
