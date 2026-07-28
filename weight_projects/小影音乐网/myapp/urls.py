from django.urls import path
from . import views

urlpatterns = [
    path('', views.index_view, name='index'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('articles/', views.article_list_view, name='article_list'),
    path('articles/create/', views.article_create_view, name='article_create'),
    path('articles/<int:pk>/', views.article_detail_view, name='article_detail'),
    path('articles/<int:pk>/edit/', views.article_edit_view, name='article_edit'),
    path('articles/<int:pk>/delete/', views.article_delete_view, name='article_delete'),
]
