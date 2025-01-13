from django.contrib import admin
from .models import Conversation, Messages


class ConversationAdmin(admin.ModelAdmin):

    list_display = ('user', 'conversation_id', 'conversation_summary')
    list_filter = ('user', 'conversation_id')

class MessageAdmin(admin.ModelAdmin):

    list_display = ('conversation_id', 'user_message', 'ai_response')
    list_filter = ('conversation_id',)

# class Messages(models.Model):
#     user_message = models.TextField()
#     ai_response = models.TextField()
#     conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE)
#     created_at = models.DateTimeField(auto_now_add=True)
admin.site.register(Messages, MessageAdmin)
admin.site.register(Conversation, ConversationAdmin)
