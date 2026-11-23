import os
from celery import Celery

# Set default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('driverxtra')

# Configure Celery using settings from django.conf.settings with 'CELERY_' namespace.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover task modules from all registered Django apps.
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Diagnostic task to verify Celery worker pipeline connectivity."""
    print(f'Debug task executed by worker: {self.request!r}')
