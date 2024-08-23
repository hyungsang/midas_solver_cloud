from django.db import models
from django.contrib.auth.models import User
from django.contrib import messages
import os

def user_directory_path(instance, filename):
    fname, ext = os.path.splitext(filename)
    return '{0}/{1}/{2}'.format(instance.user.username, fname, filename)

def directory_path(instance, filename):
    fname, ext = os.path.splitext(filename)
    return '{0}/{1}'.format(fname, filename)

# Create your models here.
class MidasModelFile(models.Model):
    id = models.AutoField(primary_key=True)
    file = models.FileField(upload_to=directory_path)
    # user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='Model')
    type = models.CharField(max_length=10, blank=True, null=True)
    status = models.CharField(max_length=10, default='NONE')
    created_at = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=3000, blank=True, null=True)
    stdout = models.TextField(blank=True, null=True)
    executed_at = models.DateTimeField(blank=True, null=True)
    pid = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = 'Model File'
        verbose_name_plural = 'Model Files'
        ordering = ['created_at']
    
    def __str__(self):
        return self.file.name
    
class MidasConfigure(models.Model):
    # user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='Config')
    max_run = models.IntegerField(blank=False, default=4)
    gen_path = models.CharField(max_length=512, default='Input path', blank=True)    
    civil_path = models.CharField(max_length=512, default='Input path', blank=True)
    gts_path = models.CharField(max_length=512, default='Input path', blank=True)
    fea_path = models.CharField(max_length=512, default='Input path', blank=True)
    nfx_path = models.CharField(max_length=512, default='Input path', blank=True)
    # mec_path = models.CharField(max_length=512, default='Input path', blank=True)

    class Meta:
        verbose_name = 'Configuration'
        verbose_name_plural = 'Configuration'

    def __str__(self):
        return f"Configuration"