from django.db import models
from django.contrib.auth.models import User

class Conversation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    conversation_id = models.CharField(max_length=255, unique=True)
    conversation_summary = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Conversation {self.conversation_id} by {self.user.username}"

class Messages(models.Model):
    user_message = models.TextField()
    ai_response = models.TextField()
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)