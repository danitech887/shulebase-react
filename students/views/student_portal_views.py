import re
from decimal import Decimal
from datetime import datetime
from django.utils import timezone
from django.db.models import Sum, Q, Avg, Count
from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from core.models import (
    StudentInfo, GradeFeeConfig, Fee, LeaveManagement, StudentAttendance, 
    MasterSchool,Strand, SubStrandMark, LearnerCompetency, 
    Resource, LearningLog, StudentNote,TeachersRole,Announcement,
)


# --- CONSTANTS & HELPERS ---

CBC_LEVEL_MAP = {
    'EE': {'min_avg': 3.50, 'label': 'Exceeding Expectations', 'remark': 'Excellent Mastery'},
    'ME': {'min_avg': 2.50, 'label': 'Meeting Expectations', 'remark': 'Good Progress'},
    'AE': {'min_avg': 1.50, 'label': 'Approaching Expectations', 'remark': 'Needs Improvement'},
    'BE': {'min_avg': 1.00, 'label': 'Below Expectations', 'remark': 'Critical Intervention'},
}

def get_cbc_level_and_remark(avg_level):
    if avg_level is None:
        return {'level': 'N/A', 'remark': 'No Data'}
    for key, data in sorted(CBC_LEVEL_MAP.items(), key=lambda x: x[1]['min_avg'], reverse=True):
        if avg_level >= data['min_avg']:
            return {'level': key, 'label': data['label'], 'remark': data['remark']}
    return {'level': 'BE', 'label': 'Below Expectations', 'remark': 'Critical Intervention'}

def _get_student(request):
    """
    Helper to resolve the student profile from the authenticated user.
    Assumes your User model has school_id and registration_no.
    """
    return StudentInfo.objects.filter(
        school_id=request.user.school_id, 
        registration_no=request.user.registration_no
    ).first()

def _get_parent_associated_students(request):
    """
    Helper to retrieve all StudentInfo objects associated with the authenticated parent.
    This is a placeholder and assumes a relationship exists between the User model
    (representing the parent) and StudentInfo (e.g., through a ForeignKey or ManyToMany).
    You would need to implement the actual logic based on your Parent/Student model relationships.
    For example:
    return StudentInfo.objects.filter(school_id=request.user.school_id, parent_user=request.user)
    """
    return StudentInfo.objects.none() # Return an empty queryset as a safe default

# --- API VIEWS ---

class StudentPortalDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        student = _get_student(request)
        if not student:
            return Response({'detail': 'Student profile not found.'}, status=404)

        term = request.query_params.get('term', 'Term 1')
        year = request.query_params.get('year', str(datetime.now().year))

        # Fees
        grade_obj = get_object_or_404(GradeFeeConfig, school_id=student.school_id, grade=student.grade)
        fee_records = Fee.objects.filter(registration_no=student.registration_no, term=term)
        total_paid = fee_records.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        # Attendance
        attendance = StudentAttendance.objects.filter(registration_no=student.registration_no)
        total_days = attendance.count()
        present_days = attendance.filter(status='Present').count()
        
        # Leaves
        leaves = LeaveManagement.objects.filter(student_id=student)

        return Response({
            'summary': {
                'fees': {
                    'expected': grade_obj.expected_fee,
                    'paid': total_paid,
                    'balance': grade_obj.expected_fee - total_paid
                },
                'attendance': {
                    'percentage': (present_days / total_days * 100) if total_days > 0 else 0,
                    'present': present_days,
                    'absent': total_days - present_days
                },
                'leaves': {
                    'total': leaves.count(),
                    'approved': leaves.filter(status='Approved').count(),
                    'pending': leaves.filter(status='Pending').count()
                }
            },
            'term_choices': ['Term 1', 'Term 2', 'Term 3'],
            'current_year': datetime.now().year
        })

class StudentPortalFeesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        student = _get_student(request)
        term = request.query_params.get('term', 'Term 1')
        
        grade_obj = get_object_or_404(GradeFeeConfig, school_id=student.school_id, grade=student.grade)
        fee_records = Fee.objects.filter(registration_no=student.registration_no, term=term).order_by('-date_of_payment')
        total_paid = fee_records.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        return Response({
            'expected_fee': grade_obj.expected_fee,
            'total_paid': total_paid, 
            'balance': grade_obj.expected_fee - total_paid,
            'history': [{'id': f.id, 'amount': f.amount, 'date': f.date_of_payment, 'term': f.term} for f in fee_records]
        })

class StudentPortalAttendanceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        student = _get_student(request)
        term = request.query_params.get('term', 'Term 1')
        
        records = StudentAttendance.objects.filter(
            registration_no=student.registration_no, term=term
        ).order_by('-date_of_attendance')

        # Find Class Teacher
        teacher_role = TeachersRole.objects.filter(
            school_id=student.school_id, grade=student.grade, 
            stream=student.stream, type_of_teacher='Class Teacher'
        ).select_related('registration_no').first()

        present = records.filter(status='Present').count()
        total = records.count()

        return Response({
            'records': [{'date': r.date_of_attendance, 'status': r.status} for r in records],
            'stats': {
                'present': present,
                'absent': total - present,
                'percentage': (present / total * 100) if total > 0 else 0
            },
            'class_teacher': f"{teacher_role.registration_no.first_name} {teacher_role.registration_no.surname}" if teacher_role else "N/A"
        })

class StudentPortalAcademicsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        student = _get_student(request)
        term = request.query_params.get('term', 'Term 1')
        year = request.query_params.get('year', str(datetime.now().year))

        base_marks = SubStrandMark.objects.filter(student=student, term=term, year=year)

        # Learning Area Performance
        subject_summaries = []
        summary_qs = base_marks.values('sub_strand__strand__subject').annotate(
            avg_score=Avg('score'), avg_level=Avg('level')
        )

        for item in summary_qs:
            subj = item['sub_strand__strand__subject']
            t_role = TeachersRole.objects.filter(grade=student.grade, subject__icontains=subj).first()
            
            subject_summaries.append({
                'subject': subj,
                'score': item['avg_score'],
                'level': item['avg_level'],
                'rating': get_cbc_level_and_remark(item['avg_level'])['level'],
                'teacher': f"{t_role.registration_no.first_name}" if t_role else "N/A"
            })

        # Competencies
        competencies = LearnerCompetency.objects.filter(student=student, term=term, year=year)
        
        # Educational Resources
        resources = Resource.objects.filter(grade=student.grade, stream=student.stream, term=term)
        

        # Distribution & Aggregates
        level_avg = base_marks.aggregate(Avg('level'))['level__avg'] or 0
        score_avg = base_marks.aggregate(Avg('score'))['score__avg'] or 0
        rating_info = get_cbc_level_and_remark(level_avg)

        return Response({
            'overall_mean_score': round(score_avg, 2),
            'overall_mean_level': round(level_avg, 2),
            'overall_rating': rating_info['level'],
            'overall_remark': rating_info['remark'],
            'subjects': subject_summaries,
            'competencies': [
                {
                    'competency': c.competency, 
                    'level': c.level, 
                    'rating': get_cbc_level_and_remark(c.level)['level'],
                    'comment': c.comment
                } for c in competencies
            ],
            'resources': [{'id': r.id, 'title': r.title, 'type': r.resource_type, 'url_or_file': r.url_or_file} for r in resources],
            'year_choices': list(SubStrandMark.objects.filter(student=student).values_list('year', flat=True).distinct())
        })

class StudentPortalLeaveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        student = _get_student(request)
        term = request.query_params.get('term', 'Term 1')
        records = LeaveManagement.objects.filter(student_id=student, term=term).order_by('-date_of_leave')
        
        return Response({
            'history': [{'id': r.id, 'date': r.date_of_leave, 'status': r.status, 'reason': r.other_reason} for r in records],
            'stats': {
                'approved': records.filter(status='Approved').count(),
                'pending': records.filter(status='Pending').count(),
                'rejected': records.filter(status='Rejected').count()
            }
        })

    def post(self, request):
        student = _get_student(request)
        LeaveManagement.objects.create(
            school_id=student.school_id,
            student_id=student,
            date_of_leave=request.data.get('date_of_leave'),
            reason='Other Reason',
            other_reason=request.data.get('reason'),
            phone=student.phone,
            status='Pending'
        )
        return Response({'detail': 'Leave application submitted successfully.'}, status=status.HTTP_201_CREATED)

class StudentAnnouncementsAPI(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        student = _get_student(request)
        announcements = Announcement.objects.filter(
            Q(target_audience__icontains='Students') | Q(target_audience__icontains=student.registration_no),
            school_id=student.school_id
        ).order_by('-created_at')
        
        return Response([
            {
                'id': a.id, 
                'title': a.title, 
                'body': a.body, 
                'date': a.created_at
            } for a in announcements
        ])



class StudentResourceAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_student(self, request):
        return StudentInfo.objects.filter(
            school_id=request.user.school_id, 
            registration_no=request.user.registration_no
        ).first()

    def get(self, request):
        """Get all resources assigned to the student's grade/stream/term."""
        student = self._get_student(request)
        if not student:
            return Response({'detail': 'Student record not found.'}, status=404)

        term = request.query_params.get('term', 'Term 1')
        
        # Fetch resources matching student's class
        resources = Resource.objects.filter(
            school_id=student.school_id,
            grade=student.grade,
            stream=student.stream,
            term=term
        ).order_by('-created_at')

        

        # Fetch progress logs for these resources
        logs = LearningLog.objects.filter(student=student, resource__in=resources)
        log_map = {log.resource_id: {'progress': log.progress, 'completed': log.completed} for log in logs}

        data = []
        for res in resources:
            data.append({
                'id': res.id,
                'title': res.title,
                'subject': res.subject,
                'type': res.resource_type,
                'url_or_file': res.url_or_file,
                'thumbnail': res.thumbnail.url if res.thumbnail else None,
                'progress': log_map.get(res.id, {'progress': 0, 'completed': False})
            })
        print(data)

        return Response(data)

    def post(self, request):
        """Update progress when a student watches a video or reads a book."""
        student = self._get_student(request)
        resource_id = request.data.get('resource_id')
        progress_val = request.data.get('progress', 0)
        
        resource = get_object_or_404(Resource, id=resource_id)
        
        # Update or create the log
        log, created = LearningLog.objects.update_or_create(
            student=student,
            resource=resource,
            defaults={
                'progress': progress_val,
                'completed': True if int(progress_val) >= 100 else False
            }
        )

        return Response({
            'detail': 'Progress updated.',
            'progress': log.progress,
            'completed': log.completed
        })


class StudentResourceTrackAPIView(APIView):
    """Track resource access (simple GET) and return current progress/log."""
    permission_classes = [IsAuthenticated]

    def get(self, request, resource_id):
        student = StudentInfo.objects.filter(
            school_id=request.user.school_id,
            registration_no=request.user.registration_no
        ).first()
        if not student:
            return Response({'detail': 'Student record not found.'}, status=404)

        resource = Resource.objects.filter(id=resource_id, school_id=student.school_id).first()
        if not resource:
            return Response({'detail': 'Resource not found.'}, status=404)

        log, created = LearningLog.objects.get_or_create(
            student=student,
            resource=resource,
            defaults={'progress': 0, 'completed': False}
        )
        # Update watched_at to now
        log.watched_at = timezone.now()
        log.save()

        return Response({'id': log.id, 'progress': log.progress, 'completed': log.completed})


class StudentSubjectStrandsAPIView(APIView):
    """Return strands and their sub-strands for a given subject visible to students."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        student = _get_student(request)
        if not student:
            return Response({'detail': 'Student record not found.'}, status=404)
        subject = request.query_params.get('subject', '').strip()
        term = request.query_params.get('term', '').strip() or 'Term 1'
        year = request.query_params.get('year', '').strip() or str(datetime.now().year)
        if not subject:
            return Response({'detail': 'subject query param required.'}, status=400)
        strands_qs = Strand.objects.filter(school_id=student.school_id, subject__iexact=subject).order_by('name')
        result = []
        for st in strands_qs:
            sub_qs = st.sub_strands.all().order_by('created_at')
            subs = []
            for ss in sub_qs:
                mark = SubStrandMark.objects.filter(student=student, sub_strand=ss, term=term, year=year).first()
                subs.append({
                    'id': ss.id,
                    'name': ss.name,
                    'description': ss.description,
                    'score': mark.score if mark else None,
                    'level': mark.level if mark else None,
                    'remark': mark.remark if mark else None,
                })

            result.append({
                'id': st.id,
                'name': st.name,
                'description': st.description,
                'sub_strands': subs,
            })

        return Response({'subject': subject, 'term': term, 'year': year, 'strands': result})


class StudentSubjectCompetenciesAPIView(APIView):
    """Return learner competencies for the authenticated student filtered by subject/term/year."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        student = _get_student(request)
        if not student:
            return Response({'detail': 'Student record not found.'}, status=404)

        subject = request.query_params.get('subject', '').strip()
        term = request.query_params.get('term', '').strip() or 'Term 1'
        year = request.query_params.get('year', '').strip() or str(datetime.now().year)

        qs = LearnerCompetency.objects.filter(student=student, term=term, year=year)
        if subject:
            qs = qs.filter(subject__iexact=subject)

        data = [
            {
                'id': c.id,
                'competency': c.competency,
                'level': c.level,
                'rating': get_cbc_level_and_remark(c.level)['level'],
                'comment': c.comment,
                'subject': c.subject,
            }
            for c in qs
        ]

        return Response({'subject': subject, 'term': term, 'year': year, 'competencies': data})


class StudentAllNotesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Fetches all notes for the student."""
        student = _get_student(request)
        if not student:
            return Response({'detail': 'Student record not found.'}, status=404)

        notes = StudentNote.objects.filter(student=student).select_related('resource').order_by('-updated_at')

        data = []
        for note in notes:
            data.append({
                'id': note.id,
                'resource': {
                    'id': note.resource.id,
                    'title': note.resource.title,
                    'type': note.resource.resource_type,
                    'url_or_file': note.resource.url_or_file,
                },
                'content': note.content,
                'updated_at': note.updated_at
            })

        return Response(data)

class StudentNoteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_student(self, request):
        return StudentInfo.objects.filter(
            school_id=request.user.school_id, 
            registration_no=request.user.registration_no
        ).first()

    def get(self, request, resource_id):
        """Retrieve a specific note for a resource."""
        student = self._get_student(request)
        note = StudentNote.objects.filter(student=student, resource_id=resource_id).first()
        
        if not note:
            return Response({'content': ''}) # Return empty if no note exists yet
            
        return Response({
            'content': note.content,
            'updated_at': note.updated_at
        })

    def post(self, request, resource_id):
        """Save or update a study note."""
        student = self._get_student(request)
        content = request.data.get('note_content')

        if content is None:
            return Response({'detail': 'Missing note content.'}, status=400)

        note, created = StudentNote.objects.update_or_create(
            student=student,
            resource_id=resource_id,
            defaults={'content': content}
        )
        return Response({
            'detail': 'Note saved successfully.',
            'updated_at': note.updated_at,
        })

    def delete(self, request, resource_id):
        """Clear a note."""
        student = self._get_student(request)
        StudentNote.objects.filter(student=student, resource_id=resource_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)