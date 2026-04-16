from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from ...students.forms import ContactForm

def contact_view(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            contact = form.save()

            subject = f"📩 {contact.subject} (from {contact.name})"
            body = f"""
            You have received a new message from {contact.name} ({contact.email}).

            Subject: {contact.subject}

            Message:
            {contact.message}
            """
            try:
                send_mail(
                    subject,
                    body,
                    settings.EMAIL_HOST_USER,
                    [settings.EMAIL_HOST_USER],
                    fail_silently=False,
                )
            except Exception:
                messages.error(request, "Failed to send your message. Please try again later.")
                return render(request, 'home/home.html', {'form': ContactForm()})

            messages.success(request, "✅ Your message was sent successfully!")
            return redirect('home')
        else:
            print('form is not valid')
    else:
        form = ContactForm()

    return render(request, 'home/home.html', {'form': form})
