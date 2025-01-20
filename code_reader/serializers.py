from rest_framework import serializers
from .models import Project, File, ChangeRequested, Step, Plan
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

class ChangeRequestedSerializer(serializers.ModelSerializer):
    """
    Serializer for File model.
    """
    class Meta:
        model = ChangeRequested
        fields = '__all__'


class StepSerializer(serializers.ModelSerializer):
    class Meta:
        model = Step
        fields = ['id', 'title', 'detailed_description', 'pseudo_code', 'code_snippet', 'order', 'plan']


class PlanSerializer(serializers.ModelSerializer):
    steps = StepSerializer(many=True, read_only=True)  # Nested serialization for steps
    class Meta:
        model = Plan
        fields = ['id', 'change_request', 'session_name', 'created_at', 'steps']