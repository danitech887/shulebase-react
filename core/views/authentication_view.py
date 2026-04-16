from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.mail import send_mail
import random, time

from ...students.models import Users, MasterSchool


# -------------------------
# Password reset (email based)
# -------------------------

def send_reset_email(to_email, reset_code):
    subject = "Password Reset Code"
    message = f"Your password reset code is: {reset_code}\n\nThis code will expire in 10 minutes."
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@shulebase.com")
    send_mail(subject, message, from_email, [to_email], fail_silently=False)


def reset_password(request):
    """
    Two-step reset:
    1. Enter email -> send code
    2. Enter code + new password -> reset password
    """
    for _ in messages.get_messages(request):
        pass
    if request.method == "POST":
        step = request.POST.get("step")

        # STEP 1: Enter email
        if step == "email":
            email = request.POST.get("email")
            try:
                user = Users.objects.get(email=email)
                reset_code = str(random.randint(100000, 999999))
                request.session["reset_email"] = email
                request.session["reset_code"] = reset_code
                request.session["reset_code_expiry"] = int(time.time()) + 600
                send_reset_email(email, reset_code)
                messages.success(request, "A reset code has been sent to your email.")
                return redirect("reset_password")
            except Users.DoesNotExist:
                messages.error(request, "No user with that email was found.")

        # STEP 2: Confirm reset
        elif step == "confirm":
            code = request.POST.get("code")
            new_password = request.POST.get("new_password")
            confirm_password = request.POST.get("confirm_password")

            saved_code = request.session.get("reset_code")
            expiry = request.session.get("reset_code_expiry")
            email = request.session.get("reset_email")

            if not (saved_code and expiry and email):
                messages.error(request, "Reset session expired. Please try again.")
                return redirect("reset_password")

            if int(time.time()) > expiry:
                messages.error(request, "Reset code expired. Please request again.")
                request.session.flush()
                return redirect("reset_password")

            if code != saved_code:
                messages.error(request, "Invalid reset code.")
                return redirect("reset_password")

            if new_password != confirm_password:
                messages.error(request, "Passwords do not match.")
                return redirect("reset_password")

            try:
                user = Users.objects.get(email=email)
                user.set_password(new_password)
                user.save()
                request.session.flush()
                messages.success(request, "Password reset successful. Please login.")
                return redirect("login")
            except Users.DoesNotExist:
                messages.error(request, "Something went wrong.")

    return render(request, "user/password_reset.html")


# -------------------------
# Login / Logout
# -------------------------

def unified_login(request):
    for _ in messages.get_messages(request):
        pass
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            school = MasterSchool.objects.filter(id = user.school.id).first()
            # Store basic info in session
            request.session["role"] = user.role.lower()
            request.session["school_id"] = user.school.id
            request.session["school_name"] = user.school.school_name
            request.session["address"] = user.school.address
            request.session["contact"] = user.school.contact
            request.session["email"] = user.email
            request.session["motto"] = user.school.motto
            request.session["logo_path"] = str(user.school.logo_path.url) if user.school.logo_path else None

            # Redirect by role
            if user.role.lower() == "admin":
                next_url = request.GET.get('next', 'dashboard')
                return redirect(next_url)
            elif user.role.lower() == "teacher":
                request.session["teacher_no"] = user.teacher_no
                next_url = request.GET.get('next', 'teacher_portal')
                return redirect(next_url)
            else:
                return redirect("home")
        else:
            messages.error(request, "❌ Invalid username or password")

    return render(request, "user/login.html")


@login_required
def change_user_password(request):
    for _ in messages.get_messages(request):
        pass
    if request.method == "POST":
        old_password = request.POST.get("old_password")
        new_password = request.POST.get("new_password")
        confirm_password = request.POST.get("confirm_password")

        if new_password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return redirect("change_password")

        user = request.user
        if not user.check_password(old_password):
            messages.error(request, "Old password is incorrect.")
            return redirect("change_password")

        user.set_password(new_password)
        user.save()
        messages.success(request, "Password updated successfully.")
        return redirect("account")

    return render(request, "user/change_password.html")


def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("login")
