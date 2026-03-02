"""Job lifecycle management — tracks DRC jobs with in-memory + JSON persistence."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

from backend.config import JOBS_DIR


class JobStatus(str, Enum):
    created = "created"
    uploading = "uploading"
    uploaded = "uploaded"
    running_drc = "running_drc"
    drc_complete = "drc_complete"
    drc_failed = "drc_failed"
    fixing = "fixing"
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

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Job:
        data["status"] = JobStatus(data["status"])
        return cls(**data)


class JobManager:
    """Manages DRC jobs with filesystem-backed persistence.

    Each job gets a directory under JOBS_DIR/<job_id>/ containing:
    - job.json: metadata
    - *.gds: uploaded layout
    - *_drc.lyrdb: DRC report
    """

    def __init__(self, jobs_dir: Path = JOBS_DIR):
        self._jobs_dir = jobs_dir
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Job] = {}
        self._load_existing()

    def _load_existing(self) -> None:
        """Load existing jobs from disk."""
        if not self._jobs_dir.exists():
            return
        for job_dir in self._jobs_dir.iterdir():
            if not job_dir.is_dir():
                continue
            meta_path = job_dir / "job.json"
            if meta_path.exists():
                try:
                    with open(meta_path) as f:
                        data = json.load(f)
                    self._cache[data["job_id"]] = Job.from_dict(data)
                except (json.JSONDecodeError, KeyError):
                    pass

    def _save(self, job: Job) -> None:
        """Persist job metadata to disk."""
        job_dir = self._jobs_dir / job.job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        meta_path = job_dir / "job.json"
        with open(meta_path, "w") as f:
            json.dump(job.to_dict(), f, indent=2)

    def create(self, filename: str, pdk_name: str) -> Job:
        """Create a new job."""
        job_id = str(uuid.uuid4())[:8]
        job = Job(job_id=job_id, filename=filename, pdk_name=pdk_name)
        self._cache[job_id] = job
        self._save(job)
        return job

    def get(self, job_id: str) -> Job:
        """Get a job by ID."""
        if job_id not in self._cache:
            raise KeyError(f"Job '{job_id}' not found")
        return self._cache[job_id]

    def list_jobs(self) -> list[Job]:
        """List all jobs, most recent first."""
        return sorted(self._cache.values(), key=lambda j: j.created_at, reverse=True)

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error: str | None = None,
        **kwargs: str | int | None,
    ) -> Job:
        """Update job status and optional fields."""
        job = self.get(job_id)
        job.status = status
        job.updated_at = time.time()
        if error is not None:
            job.error = error
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)
        self._save(job)
        return job

    def job_dir(self, job_id: str) -> Path:
        """Get the directory for a job."""
        return self._jobs_dir / job_id
