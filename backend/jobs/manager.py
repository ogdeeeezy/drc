"""Job lifecycle management — tracks DRC jobs with SQLite persistence."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

from backend.config import JOBS_DIR
from backend.jobs.database import Database


class JobStatus(str, Enum):
    created = "created"
    uploading = "uploading"
    uploaded = "uploaded"
    running_drc = "running_drc"
    drc_complete = "drc_complete"
    drc_failed = "drc_failed"
    fixing = "fixing"
    fixes_applied = "fixes_applied"
    running_lvs = "running_lvs"
    lvs_complete = "lvs_complete"
    lvs_failed = "lvs_failed"
    complete = "complete"


@dataclass
class Job:
    """Represents a DRC job."""

    job_id: str
    filename: str
    pdk_name: str
    status: JobStatus = JobStatus.created
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    gds_path: str | None = None
    report_path: str | None = None
    top_cell: str | None = None
    total_violations: int = 0
    error: str | None = None
    hint: str | None = None
    iteration: int = 1
    netlist_path: str | None = None
    lvs_report_path: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Job:
        data = dict(data)  # copy to avoid mutating input
        data["status"] = JobStatus(data["status"])
        # Handle legacy data without iteration
        if "iteration" not in data:
            data["iteration"] = 1
        # Filter to valid fields only
        valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid)


class JobManager:
    """Manages DRC jobs with SQLite-backed persistence.

    Each job gets a directory under JOBS_DIR/<job_id>/ for files:
    - *.gds: uploaded/fixed layouts
    - *_drc.lyrdb: DRC reports
    """

    def __init__(
        self,
        jobs_dir: Path = JOBS_DIR,
        db_path: Path | None = None,
    ):
        self._jobs_dir = jobs_dir
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        self._db = Database(db_path or (jobs_dir / "jobs.db"))

    def create(self, filename: str, pdk_name: str) -> Job:
        """Create a new job."""
        job_id = str(uuid.uuid4())[:8]
        now = time.time()
        job = Job(
            job_id=job_id,
            filename=filename,
            pdk_name=pdk_name,
            created_at=now,
            updated_at=now,
        )
        self._db.insert(job.to_dict())
        (self._jobs_dir / job_id).mkdir(parents=True, exist_ok=True)
        return job

    def get(self, job_id: str) -> Job:
        """Get a job by ID."""
        data = self._db.get(job_id)
        if data is None:
            raise KeyError(f"Job '{job_id}' not found")
        return Job.from_dict(data)

    def list_jobs(self) -> list[Job]:
        """List all jobs, most recent first."""
        return [Job.from_dict(d) for d in self._db.list_all()]

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error: str | None = None,
        **kwargs: str | int | None,
    ) -> Job:
        """Update job status and optional fields."""
        self.get(job_id)  # verify exists
        updates: dict = {"status": status.value, "updated_at": time.time()}
        if error is not None:
            updates["error"] = error
        for key, value in kwargs.items():
            if key in Job.__dataclass_fields__:
                updates[key] = value
        self._db.update(job_id, updates)
        return self.get(job_id)

    def job_dir(self, job_id: str) -> Path:
        """Get the directory for a job."""
        d = self._jobs_dir / job_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def insert_provenance(self, **kwargs) -> int:
        """Insert a fix provenance record. Delegates to Database."""
        return self._db.insert_provenance(**kwargs)

    def get_provenance(
        self,
        job_id: str,
        iteration: int | None = None,
        action: str | None = None,
    ) -> list[dict]:
        """Get provenance records for a job."""
        return self._db.get_provenance(job_id, iteration=iteration, action=action)

    def get_provenance_by_ids(self, provenance_ids: list[int]) -> list[dict]:
        """Get provenance records by their IDs."""
        return self._db.get_provenance_by_ids(provenance_ids)

    def update_provenance_action(self, provenance_id: int, new_action: str) -> None:
        """Update the action field on a provenance record."""
        self._db.update_provenance_action(provenance_id, new_action)
