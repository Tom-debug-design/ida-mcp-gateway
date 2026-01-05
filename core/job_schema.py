from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Job:
    job_id: str
    job_type: str  # "production"
    description: str
    input_files: List[str]
    output_files: List[str]
    status: str  # created/started/completed/failed
    created_at: str
    updated_at: str
    owner: str = "ida"

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Job":
        return Job(
            job_id=d["job_id"],
            job_type=d.get("job_type", "production"),
            description=d.get("description", ""),
            input_files=d.get("input_files", []),
            output_files=d.get("output_files", []),
            status=d.get("status", "created"),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            owner=d.get("owner", "ida"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "description": self.description,
            "input_files": self.input_files,
            "output_files": self.output_files,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "owner": self.owner,
        }
