from celery import shared_task
from .utils import run_code_reader, run_file_summarizer
from .models import Project

@shared_task
def start_code_reading(project_id, execution_creation=False):
    try:
        project = Project.objects.get(id=project_id)
        run_code_reader(project, execution_creation)
    except Project.DoesNotExist:
        print(f'Project with id {project_id} does not exist')
@shared_task
def async_file_summarizer(project_id, file_path, updated_code=False):
    run_file_summarizer(project_id, file_path, updated_code)