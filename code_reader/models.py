from django.db import models
from django.contrib.auth.models import User

class Project(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    repo_path = models.CharField(max_length=1000)
    summary_output_path = models.CharField(max_length=1000)
    summary = models.TextField()
    tree_structure = models.TextField()
    zip_file = models.FileField(upload_to='uploads/', null=True, blank=True)

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