from django import forms
from .models import MidasModelFile
from .widgets import MultiFileInput

class MidasModelFileForm(forms.ModelForm):
    class Meta:
        model = MidasModelFile
        fields = ['file', 'description']