from celery import shared_task
from .utils import run_code_reader
from .models import Project

@shared_task
def start_code_reading(project_id):
    try:
        project = Project.objects.get(id=project_id)
        run_code_reader(project)
    except Project.DoesNotExist:
        print(f'Project with id {project_id} does not exist')