from django.shortcuts import render
from ...students.forms import ContactForm

def home(request):
    form = ContactForm()
    return render(request, 'home/home.html', {'form': form})

