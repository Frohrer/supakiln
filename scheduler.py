from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import time
from models import SessionLocal, ScheduledJob, ExecutionLog
from code_executor import CodeExecutor

class JobScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.executor = CodeExecutor()
        self.scheduler.start()
        self.load_existing_jobs()

    def load_existing_jobs(self):
        """Load all active jobs from the database and schedule them."""
        db = SessionLocal()
        try:
            jobs = db.query(ScheduledJob).filter(ScheduledJob.is_active == 1).all()
            for job in jobs:
                self.schedule_job(job)
        finally:
            db.close()

    def schedule_job(self, job):
        """Schedule a new job or update an existing one."""
        job_id = f"job_{job.id}"
        
        # Remove existing job if it exists
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        
        # Add new job
        self.scheduler.add_job(
            self.execute_job,
            CronTrigger.from_crontab(job.cron_expression),
            id=job_id,
            args=[job.id],
            replace_existing=True
        )

    async def execute_job(self, job_id):
        """Execute a scheduled job and log its results."""
        db = SessionLocal()
        try:
            job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
            if not job or not job.is_active:
                return

            start_time = time.time()
            
            # Execute the code
            try:
                result = self.executor.execute_code(
                    code=job.code,
                    packages=job.packages.split(',') if job.packages else [],
                    timeout=getattr(job, 'timeout', 30)  # Use job timeout or default to 30
                )
                
                execution_time = time.time() - start_time
                
                # Log the execution
                log = ExecutionLog(
                    job_id=job.id,
                    code=job.code,
                    output=result.get('output'),
                    error=result.get('error'),
                    container_id=result.get('container_id'),
                    execution_time=execution_time,
                    status='success' if result.get('success') else 'error'
                )
                
                db.add(log)
                job.last_run = datetime.utcnow()
                db.commit()
                
            except Exception as e:
                execution_time = time.time() - start_time
                log = ExecutionLog(
                    job_id=job.id,
                    code=job.code,
                    error=str(e),
                    container_id=None,
                    execution_time=execution_time,
                    status='error'
                )
                db.add(log)
                job.last_run = datetime.utcnow()
                db.commit()
                
        finally:
            db.close()

    def add_job(self, name, code, cron_expression, container_id=None, packages=None):
        """Add a new scheduled job."""
        db = SessionLocal()
        try:
            job = ScheduledJob(
                name=name,
                code=code,
                cron_expression=cron_expression,
                container_id=container_id,
                packages=','.join(packages) if packages else None
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            
            self.schedule_job(job)
            return job
        finally:
            db.close()

    def update_job(self, job_id, **kwargs):
        """Update an existing job."""
        db = SessionLocal()
        try:
            job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
            if not job:
                return None
                
            for key, value in kwargs.items():
                if hasattr(job, key):
                    setattr(job, key, value)
                    
            db.commit()
            db.refresh(job)
            
            if job.is_active:
                self.schedule_job(job)
            return job
        finally:
            db.close()

    def delete_job(self, job_id):
        """Delete a scheduled job."""
        db = SessionLocal()
        try:
            job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
            if job:
                job_id = f"job_{job.id}"
                if self.scheduler.get_job(job_id):
                    self.scheduler.remove_job(job_id)
                db.delete(job)
                db.commit()
        finally:
            db.close()

# Create global scheduler instance
scheduler = JobScheduler() 