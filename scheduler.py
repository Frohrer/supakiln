from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
import time
import logging
from models import SessionLocal, ScheduledJob, ExecutionLog, SYSTEM_USER_ID
from code_executor import CodeExecutor

logger = logging.getLogger(__name__)

class JobScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.executor = CodeExecutor()
        self.scheduler.start()
        self._initialized = False
        # Don't load existing jobs immediately - wait for explicit initialization

    def initialize(self):
        """Initialize the scheduler after database migration is complete."""
        if not self._initialized:
            self.load_existing_jobs()
            self._schedule_cleanup_job()
            self._schedule_worker_reaper()
            self._schedule_pressure_reaper()
            self._schedule_cooked_reaper()
            self._initialized = True

    def _schedule_cleanup_job(self):
        """Register the periodic cleanup job (runs every 6 hours)."""
        from cleanup import run_periodic_cleanup

        def _cleanup_wrapper():
            try:
                run_periodic_cleanup()
            except Exception:
                logger.exception("Periodic cleanup failed")

        self.scheduler.add_job(
            _cleanup_wrapper,
            IntervalTrigger(hours=6),
            id="__system_cleanup",
            replace_existing=True,
        )
        logger.info("Scheduled periodic cleanup job (every 6 hours)")

    def _schedule_worker_reaper(self):
        """Periodically kill ad-hoc workers that have been idle too long.

        Configured by two env vars:
          SUPAKILN_WORKER_IDLE_TTL_SECONDS  reap threshold; <=0 disables.
                                            Default 1800 (30 minutes).
          SUPAKILN_WORKER_REAPER_INTERVAL_SECONDS  how often to scan.
                                                   Default 60.
        """
        import os
        from services.code_executor_service import get_code_executor

        try:
            idle_ttl = float(os.environ.get("SUPAKILN_WORKER_IDLE_TTL_SECONDS", "1800"))
        except ValueError:
            idle_ttl = 1800
        try:
            interval = float(os.environ.get("SUPAKILN_WORKER_REAPER_INTERVAL_SECONDS", "60"))
        except ValueError:
            interval = 60

        if idle_ttl <= 0:
            logger.info("Worker idle reaper disabled (SUPAKILN_WORKER_IDLE_TTL_SECONDS <= 0)")
            return

        def _reap_wrapper():
            try:
                reaped = get_code_executor().reap_idle_workers(idle_ttl)
                if reaped:
                    logger.info("Reaped %d idle worker(s): %s", len(reaped), reaped)
            except Exception:
                logger.exception("Worker reaper failed")

        self.scheduler.add_job(
            _reap_wrapper,
            IntervalTrigger(seconds=interval),
            id="__worker_reaper",
            replace_existing=True,
        )
        logger.info(
            "Scheduled worker idle reaper (ttl=%.0fs, interval=%.0fs)",
            idle_ttl, interval,
        )

    def _schedule_cooked_reaper(self):
        """Periodically probe /health on every worker and evict cooked ones.

        The hot path already evicts on a cooked 503 from /exec, so this
        reaper is the backstop for two failure modes the hot path misses:

          1) The container went cooked while idle (e.g. a pid bomb in a
             previous call left orphan forks pinning the pids cgroup).
             No /exec arrives so no 503 ever fires. Without this sweep
             the worker stays in our cache indefinitely and the next
             user call inherits a wedged container.

          2) The worker process itself died without the container exiting
             (OOM of pid 1, kernel bug). Connection probes fail; the
             reaper tears down the zombie container.

        Runs often — default 30s — since the goal is "a cooked container
        is never live for more than one reaper interval". Configure with
        SUPAKILN_COOKED_REAPER_INTERVAL_SECONDS; set to 0 to disable.
        """
        import os
        from services.code_executor_service import get_code_executor

        try:
            interval = float(
                os.environ.get("SUPAKILN_COOKED_REAPER_INTERVAL_SECONDS", "30")
            )
        except ValueError:
            interval = 30.0

        if interval <= 0:
            logger.info(
                "Cooked reaper disabled "
                "(SUPAKILN_COOKED_REAPER_INTERVAL_SECONDS <= 0)"
            )
            return

        def _cooked_wrapper():
            try:
                reaped = get_code_executor().reap_cooked_workers()
                if reaped:
                    logger.warning(
                        "Cooked reaper evicted %d worker(s): %s",
                        len(reaped), reaped,
                    )
            except Exception:
                logger.exception("Cooked reaper failed")

        self.scheduler.add_job(
            _cooked_wrapper,
            IntervalTrigger(seconds=interval),
            id="__cooked_reaper",
            replace_existing=True,
        )
        logger.info("Scheduled cooked-worker reaper (interval=%.0fs)", interval)

    def _schedule_pressure_reaper(self):
        """Periodically evict idle workers when the host is under load.

        Memory pressure uses /proc/meminfo; CPU pressure uses
        /proc/loadavg. Both are host-wide (container /proc reflects the
        host's view under Docker). Two-threshold eviction with a high
        and low water avoids thrashing. Configured by:

          SUPAKILN_PRESSURE_REAPER_INTERVAL_SECONDS  scan cadence
                                                     (default 30)
          SUPAKILN_MEMORY_HIGH_WATER_PCT             memory trigger
          SUPAKILN_MEMORY_LOW_WATER_PCT              memory stop
          SUPAKILN_CPU_HIGH_WATER                    load_1m trigger
        """
        import os
        from services.code_executor_service import get_code_executor

        try:
            interval = float(
                os.environ.get("SUPAKILN_PRESSURE_REAPER_INTERVAL_SECONDS", "30")
            )
        except ValueError:
            interval = 30.0

        if interval <= 0:
            logger.info(
                "Pressure reaper disabled "
                "(SUPAKILN_PRESSURE_REAPER_INTERVAL_SECONDS <= 0)"
            )
            return

        def _pressure_wrapper():
            try:
                exec_ = get_code_executor()
                mem_reaped = exec_.reap_memory_pressure()
                if mem_reaped:
                    logger.warning(
                        "Memory-pressure reaped %d worker(s): %s",
                        len(mem_reaped), mem_reaped,
                    )
                cpu_reaped = exec_.reap_cpu_pressure()
                if cpu_reaped:
                    logger.warning(
                        "CPU-pressure reaped %d worker(s): %s",
                        len(cpu_reaped), cpu_reaped,
                    )
            except Exception:
                logger.exception("Pressure reaper failed")

        self.scheduler.add_job(
            _pressure_wrapper,
            IntervalTrigger(seconds=interval),
            id="__pressure_reaper",
            replace_existing=True,
        )
        logger.info(
            "Scheduled pressure reaper (interval=%.0fs)", interval,
        )

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
        """Execute a scheduled job and log its results.

        The job runs in its owner's worker container, and the owner's
        encrypted env vars are injected. The system user runs
        owner-less jobs (legacy rows).
        """
        db = SessionLocal()
        try:
            job = db.query(ScheduledJob).filter(ScheduledJob.id == job_id).first()
            if not job or not job.is_active:
                return

            start_time = time.time()
            owner_user_id = job.owner_user_id or SYSTEM_USER_ID

            # Pull the owner's env vars. Imported lazily to avoid a
            # circular import at module load time.
            from env_manager import EnvironmentManager
            import os
            key = None
            if os.path.exists('.env_key'):
                with open('.env_key', 'rb') as f:
                    key = f.read()
            env_vars = EnvironmentManager(db, key).get_all_variables(
                owner_user_id=owner_user_id
            )

            # Execute the code
            try:
                result = self.executor.execute_code(
                    code=job.code,
                    packages=job.packages.split(',') if job.packages else [],
                    timeout=getattr(job, 'timeout', 30),
                    language=getattr(job, 'language', None) or 'python',
                    env_vars=env_vars,
                    user_id=owner_user_id,
                )

                execution_time = time.time() - start_time

                # Log the execution
                log = ExecutionLog(
                    job_id=job.id,
                    owner_user_id=owner_user_id,
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
                    owner_user_id=owner_user_id,
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

    def add_job(
        self,
        name,
        code,
        cron_expression,
        container_id=None,
        packages=None,
        language="python",
        timeout=30,
        owner_user_id=SYSTEM_USER_ID,
    ):
        """Add a new scheduled job."""
        db = SessionLocal()
        try:
            job = ScheduledJob(
                name=name,
                code=code,
                cron_expression=cron_expression,
                container_id=container_id,
                packages=','.join(packages) if packages else None,
                language=language or "python",
                timeout=timeout,
                owner_user_id=owner_user_id,
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