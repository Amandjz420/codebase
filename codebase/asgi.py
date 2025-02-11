import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import path
from codebase.consumers import TmuxConsumer  # Replace with your app name

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codebase.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter([
            path('ws/tmux/', TmuxConsumer.as_asgi()),
        ])
    ),
})