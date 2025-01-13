from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Conversation, Messages
from code_reader.models import Project
from .serializers import ConversationSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status


class ConversationViewSet(viewsets.ModelViewSet):
    queryset = Conversation.objects.all()
    serializer_class = ConversationSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class MessagesDetailViewSet(APIView):
    def get(self, request, conversation_id):
        try:
            # Retrieve the specific conversation by primary key (id)
            conversation = Conversation.objects.get(conversation_id=conversation_id)

            # Get all messages related to this conversation
            messages = Messages.objects.filter(conversation=conversation)

            # Format the messages into the required JSON structure
            response_data = []
            for message in messages:
                # User message (from the user)
                response_data.append({
                    "message": message.user_message,
                    "position": "right"
                })

                # AI response (from the bot)
                response_data.append({
                    "message": [message.ai_response],
                    "position": "left",
                    "user": {"avatar": "/_next/static/media/chat-gpt.6414a60a.png"}
                })

            return Response(response_data, status=status.HTTP_200_OK)
        except Conversation.DoesNotExist:
            return Response({'error': 'Conversation not found'}, status=status.HTTP_404_NOT_FOUND)


"""
# Analysis results will be documented here:

# View Function/Class: ConversationViewSet
# Supported HTTP Methods: GET, POST, PUT, DELETE
# Business Logic: Utilizes Django REST framework's ModelViewSet to provide CRUD operations on Conversation objects. The perform_create method is overridden to associate the created conversation with the current authenticated user.

# View Function/Class: MessagesDetailViewSet
# Supported HTTP Methods: GET
# Business Logic: Retrieves a specific conversation by ID and fetches all messages related to this conversation. Formats the messages into a JSON structure with user messages and AI responses before returning them in the response.
"""