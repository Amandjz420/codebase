from rest_framework import serializers
from .models import Conversation, Messages

class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ['id', 'user', 'conversation_id', 'conversation_summary', 'created_at']

class MessagesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Messages
        fields = ['id', 'user_message', 'ai_response', 'summary', 'created_at']

# Request and Response Data Structures
#
# For ConversationSerializer:
# Request Body: 
# {
#     "user": "<user_id>",
#     "conversation_id": "<conversation_id>",
#     "conversation_summary": "<summary>",
#     "created_at": "<timestamp>"
# }
#
# Response Body: 
# {
#     "id": "<conversation_id>",
#     "user": "<user_id>",
#     "conversation_id": "<conversation_id>",
#     "conversation_summary": "<summary>",
#     "created_at": "<timestamp>"
# }
#
# For MessagesSerializer:
# Request Body: 
# {
#     "user_message": "<user_message>",
#     "ai_response": "<ai_response>",
#     "summary": "<summary>",
#     "created_at": "<timestamp>"
# }
#
# Response Body:
# {
#     "id": "<message_id>",
#     "user_message": "<user_message>",
#     "ai_response": "<ai_response>",
#     "summary": "<summary>",
#     "created_at": "<timestamp>"
# }