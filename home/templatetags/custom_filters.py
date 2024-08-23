import os
from django import template

register = template.Library()

@register.filter
def basename(value):
    return os.path.basename(value)

@register.filter
def truncate_chars(value, num):
    if len(value) > num:
        return value[:num] + '...'
    return value