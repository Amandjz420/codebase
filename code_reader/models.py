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

    def save(self, *args, **kwargs):
        # Check if there's a new zip file uploaded
        if self.zip_file:
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

        # Call the parent class save method
        super().save(*args, **kwargs)

class File(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    path = models.CharField(max_length=500)
    summary = models.TextField()
    content = models.TextField()
    analysis = models.TextField()

class ImageUpload(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    image = models.ImageField(upload_to='images/')
    extracted_content = models.TextField()
    uploaded_at = models.DateTimeField(auto_now_add=True)