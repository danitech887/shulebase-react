from django.shortcuts import get_object_or_404, redirect,render
from ..models import Resource, LearningLog,StudentInfo,StudentNote

from django.shortcuts import get_object_or_404, redirect
from django.http import JsonResponse
import os

import re

def track_resource_ajax(request, id):
    """
    This view handles the 'Watch Lesson' click for videos.
    It returns JSON so the badge can update without a page refresh.
    """
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.method == 'GET':
        resource = get_object_or_404(Resource, id=id)
        
        # Log the learning activity
        LearningLog.objects.get_or_create(
            student=request.user,
            resource=resource
        )
        
        return JsonResponse({'status': 'success', 'message': 'Progress tracked'})
    return JsonResponse({'status': 'error'}, status=400)


from django.shortcuts import get_object_or_404, redirect
from django.http import FileResponse, HttpResponse
import requests

import re
import os
from django.shortcuts import get_object_or_404, redirect
from django.http import FileResponse
from ..models import Resource, LearningLog

def extract_youtube_id(url):
    """Helper to ensure we only redirect to the 11-char ID."""
    if not url: return None
    regex = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(regex, url)
    return match.group(1) if match else url

def track_and_open_resource(request, id):
    resource = get_object_or_404(Resource, id=id)
    
    # Log progress for the 'Completed' badge
    student = get_object_or_404(StudentInfo.objects.filter(registration_no = request.session.get('registration_no')))
    LearningLog.objects.get_or_create(student=student, resource=resource)
    
    # Handle PDF Books (Download/Inline)
    if resource.resource_type == 'book':
        if hasattr(resource, 'file') and resource.file:
            return FileResponse(
                resource.file.open('rb'), 
                as_attachment=True, 
                filename=os.path.basename(resource.file.name)
            )
        # Fallback to URL if no local file exists
        return redirect(resource.url_or_file)

    # Handle Videos: Extract ID to prevent broken playlist links
    if resource.resource_type == 'video':
        video_id = extract_youtube_id(resource.url_or_file)
        return redirect(f'https://www.youtube.com/watch?v={video_id}')
    
    return redirect('learning_hub')

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt # Use only if you aren't passing the CSRF token in the AJAX header
def update_video_progress(request, id):
    """
    Receives percentage updates from the YouTube API in the background.
    """
    if request.method == 'POST':
        progress = int(request.POST.get('progress', 0))
        resource = get_object_or_404(Resource, id=id)
        registration_no = request.session.get('registration_no')
        student = get_object_or_404(StudentInfo, registration_no=registration_no)
        
        log, created = LearningLog.objects.get_or_create(
            student=student, 
            resource=resource
        )
        
        # Only update if the student has watched more than previously recorded
        if progress > log.progress:
            log.progress = progress
            log.save()
            
        return JsonResponse({
            'status': 'success', 
            'current_progress': log.progress
        })
    return JsonResponse({'status': 'error'}, status=400)
from django.db.models import Prefetch
@csrf_exempt
def save_student_note(request, id):
    if request.method == 'POST':
        content = request.POST.get('note_content', '')
        resource = get_object_or_404(Resource, id=id)
        reg_no = request.session.get('registration_no')
        student = get_object_or_404(StudentInfo, registration_no=reg_no)
        
        note, created = StudentNote.objects.update_or_create(
            student=student, 
            resource=resource,
            defaults={'content': content}
        )
        return JsonResponse({'status': 'success', 'message': 'Note saved!'})
    
    # Optional: GET request to fetch existing note
    return JsonResponse({'status': 'error'}, status=400)

def get_student_note(request):
    """Fetches the existing note for a student to display in the modal"""
    reg_no = request.session.get('registration_no')
    student = get_object_or_404(StudentInfo, registration_no=reg_no)
    
    # Try to find an existing note, or return empty
    note = StudentNote.objects.filter(student=student)
    return JsonResponse({'content': note.content if note else ""})

def get_student_notes(request): 
    """Fetches all notes for the student for the notes modal"""
    reg_no = request.session.get('registration_no')
    student = get_object_or_404(StudentInfo, registration_no=reg_no)
    
    notes = StudentNote.objects.filter(student=student).select_related('resource').order_by('-updated_at')
    
    data = []
    for note in notes:
        data.append({
            'resource_title': note.resource.title,
            'content': note.content,
            'created_at': note.updated_at.isoformat()
        })
    
    return JsonResponse({'notes': data})
def learning_hub_view(request):
    reg_no = request.session.get('registration_no')
    student = get_object_or_404(StudentInfo, registration_no=reg_no)
    grade = student.grade
    school_id = request.session.get('school_id')
    
    # Prefetch only the log for the current student to use in the template
    user_logs = LearningLog.objects.filter(student=student)
    resources = Resource.objects.filter(grade=grade,school_id = school_id).prefetch_related(
        Prefetch('learninglog_set', queryset=user_logs, to_attr='user_log')
    ).order_by('-created_at')

    # IDs for the simple "Downloaded" check for books
    viewed_ids = user_logs.values_list('id', flat=True)

    context = {
        'resources': resources,
        'grade': grade,
        'viewed_ids': list(viewed_ids),
    }
    return render(request, 'students/student_portal/learning_resources.html', context)
