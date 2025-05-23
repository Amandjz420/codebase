from rest_framework import serializers
from .models import Project, File
from django.contrib.auth.models import User

class ProjectSerializer(serializers.ModelSerializer):
    """
    Serializer for Project model.
    """
    class Meta:
        model = Project
        fields = '__all__'


class FileSerializer(serializers.ModelSerializer):
    """
    Serializer for File model.
    """
    class Meta:
        model = File
        fields = '__all__'


class DocumentDetailFetchSerializer(serializers.Serializer):
    """
    Serializer for fetching document details based on project ID and specific fields.
    Fields:
    - project_id: Integer
    - fetch_field: List of choices ['summary', 'content', 'analysis']
    """
    project_id = serializers.IntegerField()
    fetch_field = serializers.ListField(
        child=serializers.ChoiceField(choices=['summary', 'content', 'analysis']),
        allow_empty=False
    )


class UserDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for User model to expose user details in JSON format.
    """
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']