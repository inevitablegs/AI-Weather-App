from django.urls import path
from . import views

urlpatterns = [
    path('', views.chatbot_view, name='chatbot'),
    path('clear/', views.clear_chat, name='clear_chat'),
]
