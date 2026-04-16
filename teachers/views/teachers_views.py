import calendar
from collections import defaultdict
from django.db import transaction
from django.contrib.auth.hashers import make_password
from django.db.models import Count, Q
from django.db.models.functions import ExtractMonth
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import datetime

from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import (
    TeacherInfo, TeacherAttendance, TeachersRole, LearningArea,
     TeacherLeave,MasterSchool,Users,RegConfig,LearnerCompetency,LearningLog
)


from core.serializers import RoleSerializer, TeacherSerializer, TeacherLeaveSerializer


# ═══════════════════════════════════════════════════════════════
#  HELPER MIXIN
# ═══════════════════════════════════════════════════════════════

class SchoolMixin:
    """Provides a shortcut to the authenticated user's school_id."""
    @property
    def school_id(self):
        return self.request.user.school_id


# ═══════════════════════════════════════════════════════════════
#  TEACHER LIST / CREATE
#  GET  /teachers/
#  POST /teachers/
# ═══════════════════════════════════════════════════════════════

class TeacherListView(SchoolMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        search = request.GET.get('search', '').strip()
        teachers = TeacherInfo.objects.filter(school_id=self.school_id)
        if search:
            teachers = teachers.filter(
                Q(registration_no__icontains=search) |
                Q(first_name__icontains=search) |
                Q(surname__icontains=search)
            )
        serializer = TeacherSerializer(teachers, many=True)
        return Response(serializer.data)

    def post(self, request):
        data = request.data.copy()
        data['school'] = self.school_id

        username = data.get('username')
        password = data.get('password')
        email    = data.get('email')
        reg_no   = data.get('registration_no')

        if not all([username, password, email, reg_no]):
            return Response(
                {'error': 'Username, password, email, and registration number are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if Users.objects.filter(username=username).exists():
            return Response(
                {'error': f"User '{username}' already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if TeacherInfo.objects.filter(registration_no=reg_no).exists():
            return Response(
                {'error': f"Teacher '{reg_no}' already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TeacherSerializer(data=data)
        if serializer.is_valid():
            school_instance = get_object_or_404(MasterSchool, id=self.school_id)
            with transaction.atomic():
                Users.objects.create(
                    school=school_instance,
                    username=username,
                    school_name=school_instance.school_name,
                    role='Teacher',
                    password=make_password(password),
                    email=email,
                    registration_no=reg_no,
                )
                serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors or {'error': 'Invalid data'}, status=status.HTTP_400_BAD_REQUEST)


# ═══════════════════════════════════════════════════════════════
#  TEACHER DETAIL / UPDATE / DELETE
#  GET    /teachers/<reg_no>/
#  PUT    /teachers/<reg_no>/
#  DELETE /teachers/<reg_no>/
# ═══════════════════════════════════════════════════════════════

class TeacherDetailView(SchoolMixin, APIView):
    permission_classes = [IsAuthenticated]

    def _get_teacher(self, reg_no):
        return get_object_or_404(TeacherInfo, school_id=self.school_id, registration_no=reg_no)

    def get(self, request, reg_no):
        serializer = TeacherSerializer(self._get_teacher(reg_no))
        return Response(serializer.data)

    def put(self, request, reg_no):
        teacher = self._get_teacher(reg_no)
        serializer = TeacherSerializer(teacher, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, reg_no):
        teacher = self._get_teacher(reg_no)
        try:
            Users.objects.get(school_id=self.school_id, registration_no=reg_no).delete()
        except Users.DoesNotExist:
            pass
        teacher.delete()
        return Response(
            {'message': f'Teacher {reg_no} deleted successfully.'},
            status=status.HTTP_204_NO_CONTENT,
        )


# ═══════════════════════════════════════════════════════════════
#  NEXT REGISTRATION NUMBER
#  GET /teachers/next-registration/
# ═══════════════════════════════════════════════════════════════

class NextTeacherRegistrationView(SchoolMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        reg_config   = RegConfig.objects.filter(school_id=self.school_id, target_type='teacher').first()
        last_teacher = TeacherInfo.objects.filter(school_id=self.school_id).order_by('-registration_no').first()

        next_num = 1
        if last_teacher:
            try:
                last_reg = last_teacher.registration_no
                if reg_config and reg_config.reg_format in last_reg:
                    num_str  = last_reg.split(reg_config.reg_format)[-1]
                    next_num = int(num_str) + 1
                else:
                    digits   = ''.join(ch for ch in last_reg if ch.isdigit())
                    next_num = int(digits[-2:]) + 1 if digits else 1
            except Exception:
                next_num = 1

        if reg_config and reg_config.reg_format:
            next_reg_no = f"{reg_config.reg_format}{next_num:02d}"
        else:
            next_reg_no = f"SCH{self.school_id}TCH{next_num:02d}"

        return Response({'next_registration_number': next_reg_no, 'next_number': next_num})


# ═══════════════════════════════════════════════════════════════
#  REGISTRATION NUMBER FORMAT CONFIG
#  GET  /teachers/config-reg-no/
#  POST /teachers/config-reg-no/
# ═══════════════════════════════════════════════════════════════

class TeacherRegConfigView(SchoolMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_instance = get_object_or_404(MasterSchool, id=self.school_id)
        reg_config      = RegConfig.objects.filter(school=school_instance, target_type='teacher').first()
        return Response({'current_format': reg_config.reg_format if reg_config else ''})

    def post(self, request):
        reg_format = request.data.get('reg_format')
        if not reg_format:
            return Response({'error': 'Registration format is required.'}, status=400)
        if '/' in reg_format:
            return Response({'error': 'Invalid format. Use (-) instead of /'}, status=400)

        school_instance = get_object_or_404(MasterSchool, id=self.school_id)
        RegConfig.objects.update_or_create(
            school=school_instance,
            target_type='teacher',
            defaults={'reg_format': reg_format},
        )
        return Response({'message': f'Format updated to {reg_format}', 'current_format': reg_format})


# ═══════════════════════════════════════════════════════════════
#  TEACHER STATS
#  GET /teachers/stats/
# ═══════════════════════════════════════════════════════════════

class TeacherStatsView(SchoolMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.now().date()
        return Response({
            'total_teachers': TeacherInfo.objects.filter(school_id=self.school_id).count(),
            'present_today':  TeacherAttendance.objects.filter(
                school_id=self.school_id, date_of_attendance=today, status='Present').count(),
            'absent_today':   TeacherAttendance.objects.filter(
                school_id=self.school_id, date_of_attendance=today, status='Absent').count(),
        })


# ═══════════════════════════════════════════════════════════════
#  TEACHER ATTENDANCE RECORDS
#  GET  /teachers/attendance/records/
#  POST /teachers/attendance/records/
# ═══════════════════════════════════════════════════════════════

class TeacherAttendanceRecordsView(SchoolMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        records = (
            TeacherAttendance.objects
            .filter(school_id=self.school_id)
            .select_related('registration_no')
            .order_by('-date_of_attendance')
        )
        data = [
            {
                'id':              r.id,
                'teacher_name':    f"{r.registration_no.first_name} {r.registration_no.surname}",
                'registration_no': r.registration_no.registration_no,
                'date':            r.date_of_attendance,
                'status':          r.status,
                'time_in':         r.time_in,
                'term':            r.term,
            }
            for r in records
        ]
        return Response(data)

    def post(self, request):
        attendance_data = request.data.get('attendance', [])
        term            = request.data.get('term')
        date_str        = request.data.get('date')

        if not all([term, date_str, isinstance(attendance_data, list)]):
            return Response(
                {'error': 'Expects term, date, and a list of attendance records.'},
                status=400,
            )

        school_instance = get_object_or_404(MasterSchool, id=self.school_id)
        created = []
        for record in attendance_data:
            reg_no      = record.get('registration_no')
            att_status  = record.get('status')
            teacher     = get_object_or_404(TeacherInfo, school_id=self.school_id, registration_no=reg_no)

            if TeacherAttendance.objects.filter(
                school=school_instance, registration_no=teacher, date_of_attendance=date_str
            ).exists():
                continue

            att = TeacherAttendance.objects.create(
                school=school_instance,
                registration_no=teacher,
                status=att_status,
                date_of_attendance=date_str,
                time_in=record.get('time_in') if att_status == 'Present' else None,
                term=term,
            )
            created.append(att.id)

        return Response(
            {'message': f'Saved {len(created)} attendance records.'},
            status=status.HTTP_201_CREATED,
        )


# ═══════════════════════════════════════════════════════════════
#  TEACHER MONTHLY ATTENDANCE
#  GET /teachers/attendance/monthly/
# ═══════════════════════════════════════════════════════════════

class TeacherMonthlyAttendanceView(SchoolMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        current_year = datetime.now().year
        monthly_stats = (
            TeacherAttendance.objects
            .filter(school_id=self.school_id, date_of_attendance__year=current_year)
            .annotate(month=ExtractMonth('date_of_attendance'))
            .values('month')
            .annotate(
                present=Count('id', filter=Q(status='Present')),
                absent= Count('id', filter=Q(status='Absent')),
            )
            .order_by('month')
        )

        result = []
        for stat in monthly_stats:
            total = stat['present'] + stat['absent']
            rate  = round((stat['present'] / total * 100) if total > 0 else 0, 1)
            result.append({
                'month':   calendar.month_abbr[stat['month']],
                'rate':    rate,
                'present': stat['present'],
                'absent':  stat['absent'],
            })

        return Response(result)


# ═══════════════════════════════════════════════════════════════
#  TEACHER ROLES  (also handles Learning Area creation)
#  GET  /teachers/roles/
#  POST /teachers/roles/
# ═══════════════════════════════════════════════════════════════

class TeacherRolesView(SchoolMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        roles = TeachersRole.objects.filter(school_id=self.school_id).select_related('registration_no')

        LOWER_SUBJECTS  = list(LearningArea.objects.filter(school_id=self.school_id, grade_level='Lower Primary').values_list('name', flat=True).distinct())
        UPPER_SUBJECTS  = list(LearningArea.objects.filter(school_id=self.school_id, grade_level='Upper Primary').values_list('name', flat=True).distinct())
        JUNIOR_SUBJECTS = list(LearningArea.objects.filter(school_id=self.school_id, grade_level='Junior Secondary').values_list('name', flat=True).distinct())
        CATEGORY_CHOICES = ['Languages', 'Sciences', 'Humanities', 'Technical / Applied', 'Creative Arts & Sports']
        learning_areas   = list(LearningArea.objects.filter(school_id=self.school_id).values('id', 'name', 'grade_level', 'category'))

        shared_meta = {
            'lower_subjects':  LOWER_SUBJECTS,
            'upper_subjects':  UPPER_SUBJECTS,
            'junior_subjects': JUNIOR_SUBJECTS,
            'category':        CATEGORY_CHOICES,
            'learning_areas':  learning_areas,
        }

        if not roles:
            return Response([shared_meta])

        data = []
        for role in roles:
            data.append({
                'id':               role.id,
                'registration_no':  role.registration_no.registration_no,
                'teacher_name':     f"{role.registration_no.first_name} {role.registration_no.surname}",
                'type_of_teacher':  role.type_of_teacher,
                'grade':            role.grade,
                'stream':           role.stream,
                'subject':          role.subject,
                **shared_meta,
            })
        return Response(data)

    def post(self, request):
        data = request.data.copy()
        data['school'] = self.school_id

        # Learning area creation
        if data.get('is_learning_area'):
            la = LearningArea.objects.create(
                school_id=self.school_id,
                name=data.get('name'),
                grade_level=data.get('grade_level'),
                category=data.get('category'),
            )
            return Response({'message': 'Learning Area configured successfully.', 'id': la.id}, status=status.HTTP_201_CREATED)

        serializer = RoleSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ═══════════════════════════════════════════════════════════════
#  TEACHER ROLE DETAIL  (also handles Learning Area update/delete)
#  PUT    /teachers/roles/<role_id>/
#  DELETE /teachers/roles/<role_id>/
# ═══════════════════════════════════════════════════════════════

class TeacherRoleDetailView(SchoolMixin, APIView):
    permission_classes = [IsAuthenticated]

    def _is_la(self, request):
        return request.data.get('is_learning_area') or request.GET.get('is_learning_area')

    def put(self, request, role_id):
        if self._is_la(request):
            la = get_object_or_404(LearningArea, id=role_id, school_id=self.school_id)
            la.name        = request.data.get('name',        la.name)
            la.grade_level = request.data.get('grade_level', la.grade_level)
            la.category    = request.data.get('category',    la.category)
            la.save()
            return Response({'message': 'Learning Area updated.'})

        role = get_object_or_404(TeachersRole, id=role_id, school_id=self.school_id)
        role.type_of_teacher = request.data.get('type_of_teacher', role.type_of_teacher)
        role.grade           = request.data.get('grade',           role.grade)
        role.stream          = request.data.get('stream',          role.stream)
        role.subject         = request.data.get('subject',         role.subject)
        role.save()
        return Response({'message': 'Role updated.'})

    def delete(self, request, role_id):
        if self._is_la(request):
            la = get_object_or_404(LearningArea, id=role_id, school_id=self.school_id)
            la.delete()
            return Response({'message': 'Learning Area deleted.'}, status=status.HTTP_204_NO_CONTENT)

        role = get_object_or_404(TeachersRole, id=role_id, school_id=self.school_id)
        role.delete()
        return Response({'message': 'Role removed.'}, status=status.HTTP_204_NO_CONTENT)


# ═══════════════════════════════════════════════════════════════
#  LEARNING AREAS  (read-only list)
#  GET /teachers/learning-areas/
# ═══════════════════════════════════════════════════════════════

class LearningAreasView(SchoolMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        areas = LearningArea.objects.filter(school_id=self.school_id).values('id', 'name', 'grade_level', 'category')
        return Response(list(areas))



# ═══════════════════════════════════════════════════════════════
#  TEACHER LEAVE DETAIL — VIEW / APPROVE / REJECT / CANCEL
#  GET    /teachers/leave/<leave_id>/   → view single leave
#  PUT    /teachers/leave/<leave_id>/   → admin approves / rejects; teacher cancels
#  DELETE /teachers/leave/<leave_id>/   → admin deletes record
# ═══════════════════════════════════════════════════════════════

class TeacherLeaveDetailView(SchoolMixin, APIView):
    permission_classes = [IsAuthenticated]

    def _get_leave(self, leave_id):
        return get_object_or_404(TeacherLeave, id=leave_id, school_id=self.school_id)

    def get(self, request, leave_id):
        leave      = self._get_leave(leave_id)
        role       = getattr(request.user, 'role', '').lower()
        # Teachers can only view their own leave
        if role == 'teacher' and leave.teacher.registration_no != request.user.registration_no:
            return Response({'error': 'Not authorised.'}, status=status.HTTP_403_FORBIDDEN)
        return Response(TeacherLeaveSerializer(leave).data)

    def put(self, request, leave_id):
        leave    = self._get_leave(leave_id)
        role     = getattr(request.user, 'role', '').lower()
        new_status = request.data.get('status')

        if role == 'teacher':
            # Teachers may only cancel their own pending leaves
            if leave.teacher.registration_no != request.user.registration_no:
                return Response({'error': 'Not authorised.'}, status=status.HTTP_403_FORBIDDEN)
            if new_status != 'Cancelled':
                return Response({'error': 'Teachers can only cancel their own leave.'}, status=status.HTTP_400_BAD_REQUEST)
            if leave.status != 'Pending':
                return Response({'error': 'Only pending leaves can be cancelled.'}, status=status.HTTP_400_BAD_REQUEST)
            leave.status = 'Cancelled'
            leave.save()
            return Response({'message': 'Leave cancelled.'})

        # Admin / principal path
        if role not in ('admin', 'principal'):
            return Response({'error': 'Not authorised.'}, status=status.HTTP_403_FORBIDDEN)

        allowed_transitions = {'Pending': ['Approved', 'Rejected'], 'Approved': ['Rejected'], 'Rejected': ['Approved']}
        if new_status not in allowed_transitions.get(leave.status, []):
            return Response(
                {'error': f"Cannot move from '{leave.status}' to '{new_status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        leave.status          = new_status
        # leave.admin_note      = request.data.get('admin_note', leave.admin_note)
        # leave.reviewed_by     = request.user.username
        leave.reviewed_on     = timezone.now().date()
        leave.save()
        return Response({'message': f'Leave {new_status.lower()} successfully.'})

    def delete(self, request, leave_id):
        role = getattr(request.user, 'role', '').lower()
        if role not in ('admin', 'principal'):
            return Response({'error': 'Not authorised.'}, status=status.HTTP_403_FORBIDDEN)
        self._get_leave(leave_id).delete()
        return Response({'message': 'Leave record deleted.'}, status=status.HTTP_204_NO_CONTENT)


# ═══════════════════════════════════════════════════════════════
#  TEACHER LEAVE STATS  (admin overview)
#  GET /teachers/leave/stats/
# ═══════════════════════════════════════════════════════════════

class TeacherLeaveStatsView(SchoolMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = TeacherLeave.objects.filter(school_id=self.school_id)
        return Response({
            'total':     qs.count(),
            'pending':   qs.filter(status='Pending').count(),
            'approved':  qs.filter(status='Approved').count(),
            'rejected':  qs.filter(status='Rejected').count(),
            'cancelled': qs.filter(status='Cancelled').count(),
        })