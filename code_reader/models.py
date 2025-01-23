import os
import zipfile

from django.conf import settings
from django.db import models
from django.contrib.auth.models import User

class Project(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    repo_path = models.CharField(max_length=1000)
    summary_output_path = models.CharField(max_length=1000)
    files_summary = models.TextField(null=True, blank=True)
    summary = models.TextField()
    tree_structure = models.TextField()
    zip_file = models.FileField(upload_to='uploads/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_zip_file = self.zip_file

    def save(self, *args, **kwargs):
        from .tasks import start_code_reading

        if len(self.repo_path) < 5:
            new_repo_path = os.path.join(settings.MEDIA_ROOT, self.name)
            os.makedirs(new_repo_path, exist_ok=True)
            print("extracting the zip archive")
            self.repo_path = new_repo_path

        # Check if a new zip file has been uploaded
        if self.zip_file and self.zip_file != self._original_zip_file:
            # Create a directory for the project in the media root
            new_repo_path = os.path.join(settings.MEDIA_ROOT, self.name)
            os.makedirs(new_repo_path, exist_ok=True)

            # Extract the zip file into the new directory
            with zipfile.ZipFile(self.zip_file, 'r') as zip_ref:
                zip_ref.extractall(new_repo_path)

            # Check if the extraction resulted in a single directory
            files = os.listdir(new_repo_path)
            if len(files) == 1 and os.path.isdir(os.path.join(new_repo_path, files[0])):
                new_repo_path = os.path.join(new_repo_path, files[0])
            if len(files) == 2 and os.path.isdir(os.path.join(new_repo_path, '__MACOSX')):
                new_repo_path = os.path.join(new_repo_path, files[0] if files[0] != '__MACOSX' else files[1])

            # Update the repo_path field
            self.repo_path = new_repo_path

            # Start the code reading task
            print("starting the code reader start_code_reading")
            start_code_reading.delay(self.id)

        # Call the parent class save method
        super().save(*args, **kwargs)
        # Update the original zip file reference after saving
        self._original_zip_file = self.zip_file

class File(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    path = models.CharField(max_length=500)
    summary = models.TextField()
    content = models.TextField()
    updated_code = models.TextField(blank=True, null=True)
    analysis = models.TextField()
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    is_file_type = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class ImageUpload(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    image = models.ImageField(upload_to='images/')
    extracted_content = models.TextField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class ChangeRequested(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    user_initial_query = models.TextField()
    feedback = models.TextField(null=True, blank=True)
    document_list = models.TextField(null=True, blank=True)
    description = models.TextField() # Store the steps or description of the change
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    def __str__(self):
        return f"Change for {self.project.name} at {self.created_at}"

class Plan(models.Model):
    change_request = models.ForeignKey("ChangeRequested", on_delete=models.CASCADE, related_name="plans")
    session_name = models.TextField()
    firebase_chat_id = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Plan for Change Request ID {self.change_request.id}"


class Step(models.Model):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="steps")
    title = models.CharField(max_length=255)
    detailed_description = models.TextField()
    pseudo_code = models.TextField(null=True, blank=True)
    code_snippet = models.TextField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0)  # For step ordering

    def __str__(self):
        return f"Step {self.order}: {self.title}"