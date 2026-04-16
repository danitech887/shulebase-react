
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect,get_object_or_404
from django.contrib import messages
from django.db.models import Sum
from django.utils.timezone import now
from datetime import datetime
from decimal import Decimal
from calendar import month_abbr
from django.db.models.functions import ExtractMonth, ExtractYear

from rest_framework.decorators import api_view, permission_classes 
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from ..serializers import StudentSerializer

from core.models import StudentInfo,GradeStreamConfig,GradeFeeConfig,Fee,StudentAttendance,LeaveManagement
from core.models import TeacherInfo,TeacherAttendance



@api_view(['GET'])
@permission_classes([AllowAny])
def dashboard(request):
    if not request.user.is_authenticated:
        return Response({"error": "Unauthorized"}, status=401)
    
    school_id = request.user.school_id
    today = now().date()
    term = request.GET.get('term', '').strip()
    year_param = request.GET.get('year', '').strip()
    year = int(year_param) if year_param.isdigit() else datetime.now().year
    grade = request.GET.get('grade', '').strip()
    stream = request.GET.get('stream', '').strip()

    # --- Core stats ---
    student_filters = {'school_id': school_id}
    if grade:
        student_filters['grade'] = grade
    if stream:
        student_filters['stream'] = stream
    students = StudentInfo.objects.filter(**student_filters).count()
    
    teachers = TeacherInfo.objects.filter(school_id=school_id).count()
    present_teachers = TeacherAttendance.objects.filter(
        school_id=school_id,
        date_of_attendance=today,
        status='Present'
    ).count()

    available_grades = list(GradeStreamConfig.objects.filter(school_id = school_id).values_list('grade',flat = True))
    available_streams = set(list(GradeStreamConfig.objects.filter(school_id = school_id).values_list('stream',flat = True)))
 
    # --- Fee balances per grade ---
    grade_fees_balances = []
    grades = (
        GradeStreamConfig.objects
        .filter(school_id=school_id)
        .values_list('grade', flat=True)
        .distinct()
        .order_by('grade')
    )
    if grade:
        grades = [g for g in grades if g == grade]

    students_per_grade = {}
    for g in grades:
        count = StudentInfo.objects.filter(school_id=school_id, grade=g, **({'stream': stream} if stream else {})).count()
        students_per_grade[g] = count
    print("Students per grade:", students_per_grade) 
    for g in grades:
        grade_obj = GradeFeeConfig.objects.filter(school_id=school_id, grade=g).first()
        if not grade_obj:
            grade_fees_balances.append(0)
            continue

        expected_fee = grade_obj.expected_fee
        no_of_students = students_per_grade.get(g, 0)

        fee_filter = {
            "registration_no__in": StudentInfo.objects
                .filter(school_id=school_id, grade=g, **({'stream': stream} if stream else {}))
                .values_list('registration_no', flat=True)
        }

        if term:
            fee_filter["term"] = term
            fee_filter["year"] = year

        total_paid = Fee.objects.filter(school_id=school_id, **fee_filter)\
                        .aggregate(Sum('amount'))['amount__sum'] or 0

        grade_balance = (expected_fee * Decimal(no_of_students)) - Decimal(total_paid)
        grade_fees_balances.append(grade_balance)

    total_balance = sum(grade_fees_balances)

    # --- Global Fees ---
    fee_query = Fee.objects.filter(school_id=school_id)
    if term:
        fee_query = fee_query.filter(term=term, year=year)
    if grade:
        fee_query = fee_query.filter(registration_no__grade=grade)
    if stream:
        fee_query = fee_query.filter(registration_no__stream=stream)
    fee_paid = fee_query.aggregate(Sum('amount'))['amount__sum'] or 0

    # --- Leave ---
    leave_query = LeaveManagement.objects.filter(school_id=school_id, return_date__isnull=True)
    if term:
        leave_query = leave_query.filter(term=term, year=year)
    if grade:
        leave_query = leave_query.filter(student_id__grade=grade)
    if stream:
        leave_query = leave_query.filter(student_id__stream=stream)
    leave_count = leave_query.count()

    # --- Student Attendance ---
    att_filter = {'school': school_id, 'date_of_attendance': today, 'status': 'Present'}
    if term:
        att_filter['term'] = term
    if grade:
        att_filter['registration_no__grade'] = grade
    if stream:
        att_filter['registration_no__stream'] = stream

    present_students = StudentAttendance.objects.filter(**att_filter).count()

    attendance_percentage = (
        (present_students * 100) / students if students else 0
    )

    # --- FINAL students RESPONSE ---
    
    data = {
        "students": students,
        "students_per_grade": students_per_grade,
        "teachers": teachers,
        "present_teachers": present_teachers,
        "present_students": present_students,
        "attendance_percentage": round(attendance_percentage, 2),
        "fee_paid": float(fee_paid),
        "fee_balance": float(total_balance),
        "leave_count": leave_count,
        "year": year,
        "term": term or None,
        "available_grades": available_grades,
        "available_streams": available_streams
    }

    return Response(data) 


"""
Attendance Daily Summary View
Backs the React AttendanceChart component at: GET attendance/daily-summary/

Returns the last 7 days of student attendance data, one entry per day,
with present/absent/total counts and a computed attendance rate.

URL (add to urlpatterns):
    path('attendance/daily-summary/', AttendanceDailySummaryView.as_view(), name='attendance-daily-summary'),
"""

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models import Count, Q
from datetime import datetime, timedelta

# Adjust this import to match your project layout


class AttendanceDailySummaryView(APIView):
    """
    GET attendance/daily-summary/

    Returns attendance statistics for each of the last 7 days (today inclusive).
    Days with no records are included with zeroed counts so the chart always
    renders a full week.

    Optional query params:
        days    int  – how many days to look back (default: 7, max: 30)
        grade   str  – filter by grade (e.g. "Grade 4")
        stream  str  – filter by stream (e.g. "East")
        term    str  – filter by term  (e.g. "Term 1")

    Response shape (array ordered oldest → newest):
    [
        {
            "date":    "2025-04-01",          # ISO date string
            "day":     "Tue",                 # abbreviated weekday
            "present": 142,
            "absent":  8,
            "total":   150,
            "rate":    94.67                  # present / total * 100, 2 d.p.
        },
        ...
    ]
    """

    permission_classes = [IsAuthenticated]

    MAX_DAYS = 30
    DEFAULT_DAYS = 7

    def get(self, request):
        school_id = request.user.school_id

        # ── Parse optional query params ───────────────────────────────────────
        try:
            days = min(int(request.GET.get('days', self.DEFAULT_DAYS)), self.MAX_DAYS)
        except (ValueError, TypeError):
            days = self.DEFAULT_DAYS

        grade  = request.GET.get('grade',  '').strip()
        stream = request.GET.get('stream', '').strip()
        term   = request.GET.get('term',   '').strip()

        # ── Date range: today going back `days` days ──────────────────────────
        today      = datetime.now().date()
        start_date = today - timedelta(days=days - 1)   # inclusive of today

        # ── Base queryset ─────────────────────────────────────────────────────
        qs = StudentAttendance.objects.filter(
            school_id=school_id,
            date_of_attendance__gte=start_date,
            date_of_attendance__lte=today,
        )

        if grade:
            qs = qs.filter(registration_no__grade__iexact=grade)
        if stream:
            qs = qs.filter(registration_no__stream__iexact=stream)
        if term:
            qs = qs.filter(term__iexact=term)

        # ── Aggregate by date ─────────────────────────────────────────────────
        daily_qs = (
            qs
            .values('date_of_attendance')
            .annotate(
                present=Count('id', filter=Q(status__iexact='Present')),
                absent =Count('id', filter=Q(status__iexact='Absent')),
                total  =Count('id'),
            )
            .order_by('date_of_attendance')
        )

        # Build a lookup dict keyed by date for O(1) access
        data_map = {
            row['date_of_attendance']: row
            for row in daily_qs
        }
        available_grades = [GradeStreamConfig.objects.filter(school_id = school_id).values_list('grade',flat = True)]
        available_streams = [GradeStreamConfig.objects.filter(school_id = school_id).values_list('stream',flat = True)]
        # ── Build the full date range (fill gaps with zeros) ──────────────────
        result = []
        for offset in range(days):
            current_date = start_date + timedelta(days=offset)
            row = data_map.get(current_date)

            present = row['present'] if row else 0
            absent  = row['absent']  if row else 0
            total   = row['total']   if row else 0
            rate    = round((present / total) * 100, 2) if total > 0 else 0.0

            result.append({
                'date':    current_date.isoformat(),
                'day':     current_date.strftime('%a'),   # 'Mon', 'Tue', …
                'present': present,
                'absent':  absent,
                'total':   total,
                'rate':    rate,
                'available_grades': available_grades,
                'available_streams': available_streams
            })

        print(result)

        return Response(result)


class RecentActivitiesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get recent activities for the admin dashboard"""
        school_id = request.user.school_id
        activities = []

        def to_iso(date_obj, time_obj=None):
            if not date_obj:
                date_obj = datetime.now().date()
            if not time_obj:
                time_obj = datetime.min.time()
            return datetime.combine(date_obj, time_obj).isoformat() + "Z"

        for s in StudentInfo.objects.filter(school_id=school_id).order_by('-registration_no')[:5]:
            activities.append({
                'id': f"std_{s.registration_no}",
                'action': f"New student registered: {s.first_name} {s.surname}",
                'timestamp': to_iso(s.date_of_registration),
                'icon': '🎓',
                'type': 'primary'
            })

        for f in Fee.objects.filter(school_id=school_id).order_by('-date_of_payment', '-time')[:5]:
            activities.append({
                'id': f"fee_{f.id}",
                'action': f"Fee payment of Ksh {f.amount} received for {f.registration_no.first_name}",
                'timestamp': to_iso(f.date_of_payment, f.time),
                'icon': '💰',
                'type': 'success'
            })

        for t in TeacherInfo.objects.filter(school_id=school_id).order_by('-registration_no')[:5]:
            activities.append({
                'id': f"tch_{t.registration_no}",
                'action': f"New teacher added: {t.first_name} {t.surname}",
                'timestamp': to_iso(t.date_of_registration),
                'icon': '👩‍🏫',
                'type': 'info'
            })

        for l in LeaveManagement.objects.filter(school_id=school_id).order_by('-date_of_leave', '-time')[:5]:
            activities.append({
                'id': f"leave_{l.id}",
                'action': f"Leave applied for {l.student_id.first_name}",
                'timestamp': to_iso(l.date_of_leave, l.time),
                'icon': '📋',
                'type': 'warning'
            })

        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        return Response(activities[:10])
