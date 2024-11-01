from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('upload/', views.upload_file, name='upload_file'),
    path('configure/', views.configure_setting, name='configure'),
    path('model_list/', views.model_list_view, name='model_list'),
    path('model_console/<int:pk>/', views.model_console_view, name='model_console'),
    path('model_detail/<int:pk>/', views.model_detail_view, name='model_detail'),
    path('delete/<int:pk>/', views.delete_model, name='delete_model'),
    path('run/<int:pk>/', views.run_model, name='run_model'),
    path('stop/<int:pk>/', views.stop_model, name='stop_model'),
    path('download/<int:pk>/', views.download_model, name='download_model'),
    path('systeminfo/', views.system_info, name='system_info'),    
    path('model_view/', views.model_view, name='model_view'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
