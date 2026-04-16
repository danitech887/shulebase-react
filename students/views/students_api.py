"""
Students Endpoints - Class-Based REST Framework Views for React Frontend
"""

from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db.models import Q, Sum, Count, Avg
from decimal import Decimal
import json
from datetime import datetime, timedelta
import csv
import calendar
from django.http import HttpResponse
from calendar import month_abbr
from django.db.models.functions import ExtractMonth, ExtractYear
from core.models import *
from core.serializers import *
import json as _json


# ==================== REGISTRATION NUMBER CONFIG ====================

class ConfigRegNoView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get the registration number format for students"""
        school_id = request.user.school_id
        school_instance = get_object_or_404(MasterSchool, id=school_id)
        reg_config_obj = RegConfig.objects.filter(school=school_instance, target_type='student').first()
        current_format = reg_config_obj.reg_format if reg_config_obj else ''
        return Response({'current_format': current_format})

    def post(self, request):
        """Set the registration number format for students"""
        school_id = request.user.school_id
        school_instance = get_object_or_404(MasterSchool, id=school_id)
        reg_format = request.data.get('reg_format')
        if not reg_format:
            return Response({'error': 'Registration format is required.'}, status=400)
        if '/' in reg_format:
            return Response({'error': 'Invalid registration format. Use (-) instead of /'}, status=400)
        reg_config_obj, created = RegConfig.objects.update_or_create(
            school=school_instance,
            target_type='student',
            defaults={'reg_format': reg_format}
        )
        return Response({'message': f'Registration format updated to {reg_format}', 'current_format': reg_format})


class NextRegistrationNumberView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get the next registration number to be assigned"""
        school_id = request.user.school_id
        reg_format = RegConfig.objects.filter(school_id=school_id, target_type='student').first()
        last_student = StudentInfo.objects.filter(school_id=school_id).order_by('-registration_no').first()
        if last_student:
            try:
                last_reg = last_student.registration_no
                if reg_format and reg_format.reg_format in last_reg:
                    num_str = last_reg.split(reg_format.reg_format)[-1]
                    next_num = int(num_str) + 1
                else:
                    next_num = 1
            except Exception:
                next_num = 1
        else:
            next_num = 1

        next_reg_no = (
            f"{reg_format.reg_format}{next_num:02d}"
            if reg_format
            else f"SCH{school_id}REG{next_num:02d}"
        )
        return Response({'next_registration_number': next_reg_no, 'next_number': next_num})


# ==================== STUDENT CRUD ====================
from django.db import transaction
class StudentListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get all students with optional filters"""
        school_id = request.user.school_id
        grade = request.GET.get('grade', '').strip()
        stream = request.GET.get('stream', '').strip()
        search = request.GET.get('search', '').strip()

        students = StudentInfo.objects.filter(school_id=school_id)

        if grade:
            students = students.filter(grade__iexact=grade)
        if stream:
            students = students.filter(stream__iexact=stream)
        if search:
            students = students.filter(
                Q(registration_no__icontains=search) |
                Q(first_name__icontains=search) |
                Q(surname__icontains=search)
            )

        students = students.order_by('registration_no')
        serializer = StudentSerializer(students, many=True)
        return Response({'count': students.count(), 'students': serializer.data})

    def post(self, request):
            """Create a new student and a corresponding user account"""
            school_id = request.user.school_id
            data = request.data.copy()
            data['school'] = school_id

            # 1. Logic for generating Registration Number
            if not data.get('registration_no'):
                last_student = StudentInfo.objects.filter(school_id=school_id).order_by('-registration_no').first()
                try:
                    last_reg = last_student.registration_no if last_student else ''
                    next_num = int(last_reg.split('REG')[1]) + 1 if 'REG' in last_reg else 1
                except Exception:
                    next_num = 1
                data['registration_no'] = f"SCH{school_id}REG{next_num:02d}"

            # 2. Validation
            required_fields = ['first_name', 'second_name', 'surname', 'gender', 'date_of_birth', 'grade', 'stream', 'phone', 'address']
            for field in required_fields:
                if not data.get(field):
                    return Response({'error': f'Missing required field: {field}'}, status=status.HTTP_400_BAD_REQUEST)

            if StudentInfo.objects.filter(school_id=school_id, registration_no=data['registration_no']).exists():
                return Response(
                    {'error': f"Student with registration number {data['registration_no']} already exists"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 3. Prepare Serializers
            school_obj = MasterSchool.objects.get(id=school_id)
            users_data = {
                'username': data['registration_no'],
                'role': 'Student',
                'password': data['registration_no'], 
                'school': school_id,
                'school_name': school_obj.school_name, # Populating the extra field
                'registration_no': data['registration_no']
            }
            
            student_serializer = StudentSerializer(data=data)
            user_serializer = UserSerializer(data=users_data)

            # 4. Atomic Transaction: Both must succeed or both fail
            user_serializer = UserSerializer(data=users_data)
            student_serializer = StudentSerializer(data=data)

            with transaction.atomic():
                if user_serializer.is_valid() and student_serializer.is_valid():
                    # Save User (this now hashes the password thanks to our create override)
                    user_instance = user_serializer.save()
                    
                    # Save Student
                    student_serializer.save()
                    
                    return Response(student_serializer.data, status=status.HTTP_201_CREATED)
                
                # Combine errors for a clear response
                all_errors = {**user_serializer.errors, **student_serializer.errors}
                return Response(all_errors, status=status.HTTP_400_BAD_REQUEST)
class StudentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_student(self, request, reg_no):
        return get_object_or_404(StudentInfo, school_id=request.user.school_id, registration_no=reg_no)

    def get(self, request, reg_no):
        student = self._get_student(request, reg_no)
        return Response(StudentSerializer(student).data)

    def put(self, request, reg_no):
        student = self._get_student(request, reg_no)
        serializer = StudentSerializer(student, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, reg_no):
        student = self._get_student(request, reg_no)
        student.delete()
        return Response({'message': f'Student {reg_no} deleted successfully'}, status=status.HTTP_204_NO_CONTENT)


class StudentStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get statistics about students"""
        school_id = request.user.school_id
        students = StudentInfo.objects.filter(school_id=school_id)

        students_by_grade = {}
        for grade_obj in GradeStreamConfig.objects.filter(school_id=school_id).values('grade').distinct():
            grade = grade_obj['grade']
            students_by_grade[grade] = students.filter(grade=grade).count()

        students_by_stream = {}
        for stream_obj in GradeStreamConfig.objects.filter(school_id=school_id).values('stream').distinct():
            stream = stream_obj['stream']
            students_by_stream[stream] = students.filter(stream=stream).count()

        return Response({
            'total_students': students.count(),
            'students_by_grade': students_by_grade,
            'students_by_stream': students_by_stream,
            'total_grades': GradeStreamConfig.objects.filter(school_id=school_id).values('grade').distinct().count(),
        })



class StudentSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Search students (autocomplete)"""
        school_id = request.user.school_id
        query = (
            request.GET.get('search', '').strip()
            or request.GET.get('query', '').strip()
            or request.GET.get('grade', '').strip()
        )

        if not query:
            return Response({'students': []})

        students = StudentInfo.objects.filter(school_id=school_id).filter(
            Q(grade__icontains=query) |
            Q(registration_no__icontains=query) |
            Q(first_name__icontains=query) |
            Q(surname__icontains=query) |
            Q(email__icontains=query)
        )[:20]

        return Response({'students': StudentSerializer(students, many=True).data})


# ==================== GRADES & STREAMS ====================

class GradeStreamView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, id=None):
        school_id = request.user.school_id
        qs = GradeStreamConfig.objects.filter(school_id=school_id).order_by('grade', 'stream')
        return Response(GradeStreamSerializer(qs, many=True).data)

    def post(self, request, id=None):
        school_id = request.user.school_id
        data = request.data
        if isinstance(data, list):
            created = []
            for item in data:
                item['school'] = school_id
                ser = GradeStreamSerializer(data=item)
                if ser.is_valid():
                    gs = ser.save()
                    created.append(GradeStreamSerializer(gs).data)
            return Response({'created': created}, status=status.HTTP_201_CREATED)
        else:
            data = data.copy()
            data['school'] = school_id
            ser = GradeStreamSerializer(data=data)
            if ser.is_valid():
                gs = ser.save()
                return Response(GradeStreamSerializer(gs).data, status=status.HTTP_201_CREATED)
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, id=None):
        if id is None:
            return Response({'error': 'ID required'}, status=status.HTTP_400_BAD_REQUEST)
        school_id = request.user.school_id
        gs = get_object_or_404(GradeStreamConfig, id=id, school_id=school_id)
        ser = GradeStreamSerializer(gs, data=request.data, partial=True)
        if ser.is_valid():
            ser.save()
            return Response(ser.data)
        return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id=None):
        if id is None:
            return Response({'error': 'ID required'}, status=status.HTTP_400_BAD_REQUEST)
        school_id = request.user.school_id
        gs = get_object_or_404(GradeStreamConfig, id=id, school_id=school_id)
        gs.delete()
        return Response({'message': 'Deleted'}, status=status.HTTP_204_NO_CONTENT)


class GradesListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        gs_grades = GradeStreamConfig.objects.filter(school_id=school_id).values_list('grade', flat=True).distinct()
        st_grades = StudentInfo.objects.filter(school_id=school_id).values_list('grade', flat=True).distinct()
        grades = sorted(list(set(list(gs_grades) + list(st_grades))))
        grades = [g for g in grades if g]
        return Response({'grades': grades})


class StreamsListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        grade = request.GET.get('grade', '').strip()

        if grade:
            gs_streams = GradeStreamConfig.objects.filter(school_id=school_id, grade__iexact=grade).values_list('stream', flat=True)
            st_streams = StudentInfo.objects.filter(school_id=school_id, grade__iexact=grade).values_list('stream', flat=True)
            streams = sorted(list(set(list(gs_streams) + list(st_streams))))
            streams = [s for s in streams if s]
            return Response({'grade': grade, 'streams': streams})
        else:
            gs_streams = GradeStreamConfig.objects.filter(school_id=school_id).values_list('stream', flat=True)
            st_streams = StudentInfo.objects.filter(school_id=school_id).values_list('stream', flat=True)
            streams = sorted(list(set(list(gs_streams) + list(st_streams))))
            streams = [s for s in streams if s]
            return Response({'streams': streams})


class GradeStreamMappingView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        mapping = {}
        for grade_obj in GradeStreamConfig.objects.filter(school_id=school_id).values('grade').distinct().order_by('grade'):
            grade = grade_obj['grade']
            streams = list(
                GradeStreamConfig.objects.filter(school_id=school_id, grade__iexact=grade)
                .values_list('stream', flat=True)
                .distinct()
                .order_by('stream')
            )
            mapping[grade] = streams
        return Response(mapping)


# ==================== FEES ====================

class StudentFeesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, reg_no):
        school_id = request.user.school_id
        student = get_object_or_404(StudentInfo, school_id=school_id, registration_no=reg_no)
        grade_fee = Grade.objects.filter(school_id=school_id, name=student.grade).first()
        expected_fee = grade_fee.expected_fee if grade_fee else 0
        fees = Fee.objects.filter(school_id=school_id, registration_no=reg_no)
        total_paid = fees.aggregate(Sum('amount'))['amount__sum'] or 0
        balance = expected_fee - Decimal(total_paid)

        return Response({
            'registration_no': reg_no,
            'student_name': f"{student.first_name} {student.surname}",
            'grade': student.grade,
            'stream': student.stream,
            'expected_fee': float(expected_fee),
            'total_paid': float(total_paid),
            'balance': float(balance),
            'fee_records': [
                {
                    'id': f.id,
                    'amount': float(f.amount),
                    'term': f.term,
                    'date': f.date_of_payment.isoformat() if f.date_of_payment else None,
                    'mode': f.mode_of_payment,
                    'transaction_code': f.transaction_code if f.mode_of_payment == 'mpesa' else '',
                    'status': f.status
                } for f in fees
            ]
        })


class MonthlyFeesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        grade = request.GET.get('grade', '').strip()
        stream = request.GET.get('stream', '').strip()
        today = datetime.now().date()
        start_date = today - timedelta(days=180)

        # 2. Query Fees (Filtering for only confirmed payments)
        fees_qs = Fee.objects.filter(
            school_id=school_id,
            date_of_payment__gte=start_date,
            status='Confirmed' 
        )
        
        if grade:
            fees_qs = fees_qs.filter(registration_no__grade__iexact=grade)
        if stream:
            fees_qs = fees_qs.filter(registration_no__stream__iexact=stream)
        
        # 3. Aggregate by Year and Month (Renamed to 'p_month' and 'p_year' to avoid conflict)
        monthly_data = fees_qs.annotate(
            p_month=ExtractMonth('date_of_payment'),
            p_year=ExtractYear('date_of_payment')
        ).values('p_year', 'p_month').annotate(
            total_collected=Sum('amount')
        ).order_by('p_year', 'p_month')
        
        # 4. Convert to dictionary for O(1) lookup
        data_map = {
            (item['p_year'], item['p_month']): item['total_collected'] 
            for item in monthly_data
        }
        now_dt = datetime.now()
        result = []
        y, m = now_dt.year, now_dt.month

        for _ in range(6):
            amount = data_map.get((y, m), 0)
            result.append({
                "month": month_abbr[m],
                "collected": float(amount),
                "target": 0
            })
            m -= 1
            if m == 0:
                m = 12
                y -= 1

        result.reverse()
        return Response({"monthly": result})


class RecordPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        school_id = request.user.school_id
        school = MasterSchool.objects.get(id=school_id)
        registration_no = request.data.get('registration_no', '').strip()
        amount = request.data.get('amount')
        mode_of_payment = request.data.get('mode', 'Cash').strip()
        transaction_code = request.data.get('transaction_code', '').strip()
        term = request.data.get('term', 'Term 1').strip()
        date_of_payment = request.data.get('date_of_payment')

        if not registration_no or not amount:
            return Response({'error': 'Missing required fields: registration_no, amount'}, status=status.HTTP_400_BAD_REQUEST)

        student = get_object_or_404(StudentInfo, school_id=school_id, registration_no=registration_no)

        try:
            amount = Decimal(amount)
            if amount <= 0:
                return Response({'error': 'Amount must be greater than 0'}, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, TypeError):
            return Response({'error': 'Invalid amount format'}, status=status.HTTP_400_BAD_REQUEST)

        fee = Fee.objects.create(
            school=school,
            registration_no=student,
            amount=amount,
            mode_of_payment=mode_of_payment,
            transaction_code=transaction_code if mode_of_payment.lower() in ['mpesa', 'm-pesa'] else '',
            term=term,
            year=str(datetime.now().year),
            date_of_payment=date_of_payment if date_of_payment else datetime.now().date(),
        )

        return Response({
            'id': fee.id,
            'registration_no': student.registration_no,
            'student_name': f"{student.first_name} {student.surname}",
            'amount': float(fee.amount),
            'mode': fee.mode_of_payment,
            'date': fee.date_of_payment,
            'message': f'Payment of {amount} recorded successfully for {student.first_name} {student.surname}'
        }, status=status.HTTP_201_CREATED)


class FeeRecordsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        grade = request.GET.get('grade', '').strip()
        stream = request.GET.get('stream', '').strip()
        term = request.GET.get('term', '').strip()

        fees = Fee.objects.filter(school_id=school_id).select_related('registration_no')

        if grade:
            fees = fees.filter(registration_no__grade__iexact=grade)
        if stream:
            fees = fees.filter(registration_no__stream__iexact=stream)
        if term:
            fees = fees.filter(term__iexact=term)

        fees = fees.order_by('-date_of_payment', '-time')
        data = [{
            'id': fee.id,
            'date_of_payment': fee.date_of_payment,
            'registration_no': fee.registration_no.registration_no,
            'student_name': f"{fee.registration_no.first_name} {fee.registration_no.surname}",
            'amount': fee.amount,
            'mode_of_payment': fee.mode_of_payment,
            'term': fee.term,
            'status': fee.status,
            'transaction_code': fee.transaction_code,
        } for fee in fees]
        return Response(data, status=status.HTTP_200_OK)


class UpdateFeeStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, fee_id):
        school_id = request.user.school_id
        fee = get_object_or_404(Fee, id=fee_id, school_id=school_id)
        new_status = request.data.get('status')
        if new_status in ['Confirmed', 'Rejected']:
            fee.status = new_status
            fee.save()
            return Response({'message': f'Payment {new_status} successfully'}, status=status.HTTP_200_OK)
        return Response({'error': 'Invalid status provided'}, status=status.HTTP_400_BAD_REQUEST)


class FeesByGradeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        term = request.GET.get('term', '').strip()

        gs_grades = GradeStreamConfig.objects.filter(school_id=school_id).values_list('grade', flat=True).distinct()
        st_grades = StudentInfo.objects.filter(school_id=school_id).values_list('grade', flat=True).distinct()
        for name in set(list(gs_grades) + list(st_grades)):
            if name:
                GradeFeeConfig.objects.get_or_create(school_id=school_id, grade=name)

        grades = GradeFeeConfig.objects.filter(school_id=school_id)
        grade_data = []

        for grade in grades:
            students = StudentInfo.objects.filter(school_id=school_id, grade=grade.grade)
            fees = Fee.objects.filter(
                school_id=school_id,
                registration_no__in=students.values_list('registration_no', flat=True)
            )
            if term:
                fees = fees.filter(term__iexact=term)
            expected_fee_per_student = grade.expected_fee or Decimal('0')
            total_students = students.count()
            try:
                expected_total = float(Decimal(expected_fee_per_student) * Decimal(total_students))
            except Exception:
                expected_total = 0.0

            collected = float(fees.aggregate(Sum('amount'))['amount__sum'] or Decimal('0'))
            balance = expected_total - collected
            mpesa_amount = fees.filter(mode_of_payment='M-Pesa').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
            cash_amount = fees.filter(mode_of_payment='Cash').aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
            streams_list = GradeStreamConfig.objects.filter(school_id=school_id, grade=grade.grade).values_list('stream', flat=True).distinct()

            grade_data.append({
                'grade': grade.grade,
                'streams': len(list(streams_list)) if streams_list else 1,
                'totalStudents': total_students,
                'totalFee': int(expected_total),
                'collected': int(collected),
                'balance': int(balance),
                'mpesa': int(float(mpesa_amount)),
                'cash': int(float(cash_amount)),
                'expectedFee': int(expected_fee_per_student),
            })

        return Response(grade_data)

    def post(self, request):
        school_id = request.user.school_id
        for grade_name, expected_fee in request.data.items():
            if grade_name:
                grade_obj, _ = GradeFeeConfig.objects.update_or_create(school_id=school_id, grade=grade_name)
                try:
                    expected_fee_decimal = Decimal(expected_fee)
                    if expected_fee_decimal < 0:
                        continue 
                    grade_obj.expected_fee = expected_fee_decimal
                    grade_obj.save()
                except (ValueError, TypeError):
                    continue
        return Response({'message': 'Fee settings updated successfully'})


# ==================== ATTENDANCE ====================

class StudentAttendanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, reg_no):
        school_id = request.user.school_id
        term = request.GET.get('term', '').strip()
        student = get_object_or_404(StudentInfo, school_id=school_id, registration_no=reg_no)
        attendance = StudentAttendance.objects.filter(school_id=school_id, registration_no=reg_no)
        if term:
            attendance = attendance.filter(term=term)

        total_records = attendance.count()
        present_count = attendance.filter(status='Present').count()
        absent_count = attendance.filter(status='Absent').count()
        attendance_percentage = (present_count / total_records * 100) if total_records > 0 else 0

        return Response({
            'registration_no': reg_no,
            'student_name': f"{student.first_name} {student.surname}",
            'total_records': total_records,
            'present': present_count,
            'absent': absent_count,
            'attendance_percentage': round(attendance_percentage, 2),
            'records': [
                {
                    'id': a.id,
                    'date': a.date_of_attendance.isoformat(),
                    'status': a.status,
                    'term': a.term,
                } for a in attendance.order_by('-date_of_attendance')[:30]
            ]
        })


class StudentAttendanceByGradeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        term = request.GET.get('term', '').strip()
        grades = GradeStreamConfig.objects.filter(school_id=school_id)
        today = datetime.today().date()
        attendance_data = []

        for grade in grades:
            students = StudentInfo.objects.filter(school_id=school_id, grade=grade.grade)
            attendance_records = StudentAttendance.objects.filter(
                school_id=school_id,
                registration_no__in=students.values_list('registration_no', flat=True)
            )
            if term:
                attendance_records = attendance_records.filter(term__iexact=term)
            total_students = students.count()
            present_count = attendance_records.filter(status='Present', date_of_attendance=today).count()
            absent_count = attendance_records.filter(status='Absent', date_of_attendance=today).count()
            present_rate = (present_count / total_students * 100) if total_students > 0 else 0

            attendance_data.append({
                'grade': grade.grade,
                'totalStudents': total_students,
                'present': present_count,
                'absent': absent_count,
                'presentRate': round(present_rate, 1),
            })

        return Response(attendance_data)


class StudentMonthlyAttendanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        grade = request.GET.get('grade', '').strip()
        stream = request.GET.get('stream', '').strip()
        term = request.GET.get('term', '').strip()
        current_year = datetime.now().year
        attendance_records = StudentAttendance.objects.filter(
            school_id=school_id,
            date_of_attendance__year=current_year,
        )
        if grade:
            attendance_records = attendance_records.filter(registration_no__grade__iexact=grade)
        if stream:
            attendance_records = attendance_records.filter(registration_no__stream__iexact=stream)
        if term:
            attendance_records = attendance_records.filter(term__iexact=term)
        monthly_stats = attendance_records.annotate(
            month=ExtractMonth('date_of_attendance')
        ).values('month').annotate(
            present=Count('id', filter=Q(status='Present')),
            absent=Count('id', filter=Q(status='Absent'))
        ).order_by('month')

        result = []
        for stat in monthly_stats:
            total = stat['present'] + stat['absent']
            rate = (stat['present'] / total * 100) if total > 0 else 0
            result.append({
                'month': calendar.month_abbr[stat['month']],
                'rate': round(rate, 1),
                'present': stat['present'],
                'absent': stat['absent'],
                'late': 0,
            })
        return Response(result)


class AllStudentsAttendanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        grade = request.GET.get('grade', '').strip()
        stream = request.GET.get('stream', '').strip()
        term = request.GET.get('term', '').strip()
        status_filter = request.GET.get('status', '').strip()
        date_from = request.GET.get('date_from', '').strip()
        date_to = request.GET.get('date_to', '').strip()
        search = request.GET.get('search', '').strip()

        attendance_qs = StudentAttendance.objects.filter(school_id=school_id).select_related('registration_no')

        if grade:
            attendance_qs = attendance_qs.filter(registration_no__grade__iexact=grade)
        if stream:
            attendance_qs = attendance_qs.filter(registration_no__stream__iexact=stream)
        if term:
            attendance_qs = attendance_qs.filter(term__iexact=term)
        if status_filter:
            attendance_qs = attendance_qs.filter(status__iexact=status_filter)
        try:
            if date_from:
                attendance_qs = attendance_qs.filter(date_of_attendance__gte=datetime.fromisoformat(date_from).date())
            if date_to:
                attendance_qs = attendance_qs.filter(date_of_attendance__lte=datetime.fromisoformat(date_to).date())
        except Exception:
            pass
        if search:
            attendance_qs = attendance_qs.filter(
                Q(registration_no__registration_no__icontains=search) |
                Q(registration_no__first_name__icontains=search) |
                Q(registration_no__surname__icontains=search)
            )

        attendance_qs = attendance_qs.order_by('-date_of_attendance')
        data = []
        for record in attendance_qs:
            student = record.registration_no
            data.append({
                'registration_no': student.registration_no,
                'student_name': f"{student.first_name} {student.surname}",
                'grade': student.grade,
                'stream': student.stream,
                'date': record.date_of_attendance.isoformat(),
                'status': record.status,
                'term': record.term,
                'remarks': getattr(record, 'remarks', '') or ''
            })
        return Response(data)


class SendAttendanceNotificationsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        school_id = request.user.school_id
        payload = request.data or {}
        grade = payload.get('grade')
        stream = payload.get('stream')
        registration_no = payload.get('registration_no')

        qs = StudentInfo.objects.filter(school_id=school_id)
        if registration_no:
            qs = qs.filter(registration_no=registration_no)
        if grade:
            qs = qs.filter(grade=grade)
        if stream:
            qs = qs.filter(stream=stream)

        recipients = qs.count()
        return Response({'message': 'Notifications queued', 'recipients': recipients})


class AttendanceSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        reg_obj = RegConfig.objects.filter(school_id=school_id, target_type='attendance').first()
        if reg_obj and reg_obj.reg_format:
            try:
                data = _json.loads(reg_obj.reg_format)
            except Exception:
                data = {}
        else:
            data = {}
        return Response({'settings': data})

    def post(self, request):
        school_id = request.user.school_id
        reg_obj = RegConfig.objects.filter(school_id=school_id, target_type='attendance').first()
        payload = request.data or {}
        try:
            s = _json.dumps(payload)
        except Exception:
            return Response({'error': 'Invalid payload'}, status=400)

        if reg_obj:
            reg_obj.reg_format = s
            reg_obj.save()
        else:
            school = MasterSchool.objects.get(id=school_id)
            RegConfig.objects.create(school=school, target_type='attendance', reg_format=s)

        return Response({'message': 'Attendance settings saved', 'settings': payload})


# ==================== ACADEMICS ====================

class StudentAcademicsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, reg_no):
        school_id = request.user.school_id
        term = request.GET.get('term', '').strip()
        student = get_object_or_404(StudentInfo, school_id=school_id, registration_no=reg_no)
        marks_qs = Marks.objects.filter(school_id=school_id, registration_no__registration_no=reg_no)
        if term:
            marks_qs = marks_qs.filter(term=term)

        marks_list = [{
            'id': mark.id,
            'term': mark.term,
            'exam_type': mark.type_of_exam,
            'total_marks': mark.total_marks,
            'grade': mark.grade,
            'year': mark.year,
        } for mark in marks_qs]

        avg_marks = marks_qs.aggregate(Avg('total_marks'))['total_marks__avg'] or 0

        return Response({
            'registration_no': reg_no,
            'student_name': f"{student.first_name} {student.surname}",
            'grade': student.grade,
            'stream': student.stream,
            'average_marks': round(avg_marks, 2),
            'total_records': marks_qs.count(),
            'marks': marks_list,
        })


class AcademicsByGradeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        grades = Grade.objects.filter(school_id=school_id)
        performance_data = []

        for grade in grades:
            students = StudentInfo.objects.filter(school_id=school_id, grade=grade.name)
            marks_records = Marks.objects.filter(
                school_id=school_id,
                registration_no__in=students.values_list('registration_no', flat=True)
            )
            avg_marks = marks_records.aggregate(Avg('mean_marks'))['mean_marks__avg'] or 0
            records_count = marks_records.count()

            performance_data.append({
                'grade': grade.name,
                'averageMarks': round(avg_marks, 1),
                'totalStudents': students.count(),
                'studentsWithMarks': records_count,
                'topPerformers': marks_records.filter(mean_marks__gte=80).count() if records_count > 0 else 0,
                'averagePerformers': marks_records.filter(mean_marks__gte=50, mean_marks__lt=80).count() if records_count > 0 else 0,
                'lowPerformers': marks_records.filter(mean_marks__lt=50).count() if records_count > 0 else 0,
            })

        return Response(performance_data)


class TopStudentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        marks_records = Marks.objects.filter(school_id=school_id).select_related('registration_no').order_by('-mean_marks')[:3]
        top_students_list = [{
            'registration_no': mark.registration_no.registration_no,
            'student_name': f"{mark.registration_no.first_name} {mark.registration_no.surname}",
            'grade': mark.registration_no.grade,
            'stream': mark.registration_no.stream,
            'mean_marks': mark.mean_marks,
            'term': mark.term,
            'year': mark.year,
        } for mark in marks_records]
        return Response(top_students_list)


class GenerateReportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        term = request.GET.get('term')

        fees = Fee.objects.filter(school_id=school_id).select_related('registration_no').order_by('-date_of_payment')
        if start_date:
            fees = fees.filter(date_of_payment__gte=start_date)
        if end_date:
            fees = fees.filter(date_of_payment__lte=end_date)
        if term and term != 'undefined':
            fees = fees.filter(term=term)

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="fee_report.csv"'
        writer = csv.writer(response)
        writer.writerow(['Date', 'Student Name', 'Reg No', 'Grade', 'Amount', 'Mode', 'Term', 'Transaction Code'])
        for fee in fees:
            student = fee.registration_no
            writer.writerow([
                fee.date_of_payment,
                f"{student.first_name} {student.surname}",
                student.registration_no,
                student.grade,
                fee.amount,
                fee.mode_of_payment,
                fee.term,
                fee.transaction_code
            ])
        return response


# ==================== LEAVES ====================

class LeavesListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        leaves = LeaveManagement.objects.filter(school_id=school_id).select_related('student')
        grade = request.GET.get('grade', '').strip()
        stream = request.GET.get('stream', '').strip()
        term = request.GET.get('term', '').strip()
        status_param = request.GET.get('status', '').strip().lower()

        if grade:
            leaves = leaves.filter(student_id__grade__iexact=grade)
        if stream:
            leaves = leaves.filter(student_id__stream__iexact=stream)
        if term:
            leaves = leaves.filter(term__iexact=term)
        if status_param:
            if status_param == 'pending':
                leaves = leaves.filter(Q(status__isnull=True) | Q(status__exact='') | Q(status__iexact='pending'))
            else:
                leaves = leaves.filter(status__iexact=status_param)

        leaves = leaves.order_by('-date_of_leave')[:200]
        records = []
        for leave in leaves:
            student = leave.student
            duration = None
            try:
                if leave.date_of_leave and leave.return_date:
                    duration = (leave.return_date - leave.date_of_leave).days
            except Exception:
                duration = None

            records.append({
                'id': leave.id,
                'student': f"{getattr(student, 'first_name', '')} {getattr(student, 'second_name', '')} {getattr(student, 'surname', '')}".strip(),
                'grade': getattr(student, 'grade', ''),
                'reason': leave.reason or 'Other',
                'otherReason': getattr(leave, 'other_reason', '') or '',
                'startDate': leave.date_of_leave.isoformat() if leave.date_of_leave else None,
                'endDate': leave.return_date.isoformat() if leave.return_date else None,
                'duration': duration,
                'status': (leave.status or 'pending').lower(),
            })
        return Response(records)


class ApplyLeaveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        school_id = request.user.school_id
        school = get_object_or_404(MasterSchool, id=school_id)
        registration_no = request.data.get('registration_no')
        reason = request.data.get('reason', 'other')
        other_reason = request.data.get('otherReason', '')
        start_date = request.data.get('startDate')
        end_date = request.data.get('endDate')

        if not registration_no or not start_date:
            return Response({'error': 'Student and Start Date are required'}, status=status.HTTP_400_BAD_REQUEST)

        student = get_object_or_404(StudentInfo, school_id=school_id, registration_no=registration_no)
        reason_db = 'School Fees' if reason == 'fees' else 'Other'

        leave = LeaveManagement.objects.create(
            school=school,
            registration_no=student,
            reason=reason_db,
            other_reason=other_reason if reason_db == 'Other' else '',
            date_of_leave=start_date,
            return_date=end_date if end_date else None,
            status='approved',
            term='Term 1',
            phone=student.phone,
        )
        return Response({'message': 'Leave applied successfully', 'id': leave.id}, status=status.HTTP_201_CREATED)


class EligibleLeaveStudentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        grade = request.GET.get('grade')
        stream = request.GET.get('stream')
        reason = request.GET.get('reason')
        try:
            amount = float(request.GET.get('amount') or 0)
        except ValueError:
            amount = 0.0

        active_leaves = LeaveManagement.objects.filter(
            school_id=school_id, return_date__isnull=True
        ).values_list('student_id', flat=True)

        students = StudentInfo.objects.filter(school_id=school_id)
        if grade:
            students = students.filter(grade__iexact=grade)
        if stream:
            students = students.filter(stream__iexact=stream)
        students = students.exclude(registration_no__in=active_leaves)

        result = []
        if reason == 'fees':
            for student in students:
                grade_obj = GradeFeeConfig.objects.filter(school_id=school_id, grade=student.grade).first()
                expected = grade_obj.expected_fee if grade_obj and grade_obj.expected_fee else Decimal('0')
                paid = Fee.objects.filter(school_id=school_id, registration_no=student).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
                balance = float(expected) - float(paid)
                if balance >= amount:
                    result.append({
                        'registration_no': student.registration_no,
                        'name': f"{getattr(student, 'first_name', '')} {getattr(student, 'surname', '')}".strip(),
                        'balance': balance
                    })
        else:
            for student in students:
                result.append({
                    'registration_no': student.registration_no,
                    'name': f"{getattr(student, 'first_name', '')} {getattr(student, 'surname', '')}".strip(),
                    'balance': None
                })
        return Response(result)


class ApplyBulkLeaveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        school_id = request.user.school_id
        school = get_object_or_404(MasterSchool, id=school_id)
        student_ids = request.data.get('students', [])
        reason = request.data.get('reason', 'other')
        start_date = request.data.get('startDate', datetime.now().date())
        term = request.data.get('term', 'Term 1')
        reason_db = 'School Fees' if reason == 'fees' else 'Other'

        leaves_to_create = []
        for reg_no in student_ids:
            student = StudentInfo.objects.filter(school_id=school_id, registration_no=reg_no).first()
            if student:
                leaves_to_create.append(
                    LeaveManagement(
                        school=school,
                        student=student,
                        reason=reason_db,
                        date_of_leave=start_date,
                        status='approved',
                        term=term,
                        phone=student.phone
                    )
                )

        if leaves_to_create:
            LeaveManagement.objects.bulk_create(leaves_to_create)

        return Response({'message': f'Successfully applied leave for {len(leaves_to_create)} students'}, status=status.HTTP_201_CREATED)


class UpdateLeaveStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, leave_id):
        school_id = request.user.school_id
        leave = get_object_or_404(LeaveManagement, id=leave_id, school_id=school_id)
        new_status = request.data.get('status')
        if new_status in ['approved', 'rejected']:
            leave.status = new_status
            leave.save()
            return Response({'message': f'Leave {new_status} successfully'}, status=status.HTTP_200_OK)
        return Response({'error': 'Invalid status provided'}, status=status.HTTP_400_BAD_REQUEST)


class UpdateLeaveReturnDateView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, leave_id):
        school_id = request.user.school_id
        leave = get_object_or_404(LeaveManagement, id=leave_id, school_id=school_id)
        return_date = request.data.get('return_date')
        if not return_date:
            return Response({'error': 'Return date is required'}, status=status.HTTP_400_BAD_REQUEST)
        leave.return_date = return_date
        leave.save()
        return Response({'message': 'Return date updated successfully'}, status=status.HTTP_200_OK)


class LeavesSummaryByGradeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        term = request.GET.get('term', '').strip()
        summary = []
        for grade in GradeFeeConfig.objects.filter(school_id=school_id):
            students_qs = StudentInfo.objects.filter(school_id=school_id, grade=grade.grade)
            leaves_qs = LeaveManagement.objects.filter(
                school_id=school_id,
                student_id__in=students_qs.values_list('registration_no', flat=True)
            )
            if term:
                leaves_qs = leaves_qs.filter(term__iexact=term)
            on_leave = leaves_qs.filter(return_date__isnull=True).count()
            summary.append({
                'grade': grade.grade,
                'totalStudents': students_qs.count(),
                'onLeave': on_leave,
                'pending': 0,
                'approved': on_leave,
                'rejected': 0,
                'feeRelated': leaves_qs.filter(reason='School Fees').count(),
                'other': leaves_qs.exclude(reason='School Fees').count(),
            })
        return Response(summary)


# ==================== CBC ACADEMICS ====================

LEVEL_NAMES = {4: 'Exceeding Expectations', 3: 'Meeting Expectation', 2: 'Approaching Expectation', 1: 'Below Expectation'}
CBC_LEVEL_MAP = {
    'EE': {'min_avg': 3.5, 'label': 'Exceeding Expectations', 'remark': 'Excellent Mastery'},
    'ME': {'min_avg': 2.5, 'label': 'Meeting Expectations', 'remark': 'Good Progress'},
    'AE': {'min_avg': 1.5, 'label': 'Approaching Expectations', 'remark': 'Needs Improvement'},
    'BE': {'min_avg': 0.0, 'label': 'Below Expectations', 'remark': 'Critical Intervention'},
}


def get_cbc_level_and_remark(avg_level):
    if avg_level is None or avg_level <= 0:
        return {'level': '-', 'remark': 'No Data'}
    capped_avg = min(avg_level, 4.0)
    for code, data in sorted(CBC_LEVEL_MAP.items(), key=lambda item: item[1]['min_avg'], reverse=True):
        if capped_avg >= data['min_avg']:
            return {'level': code, 'remark': data['remark']}
    return {'level': 'BE', 'remark': CBC_LEVEL_MAP['BE']['remark']}


def get_dashboard_comparison_data(school_id, selected_term, selected_year, grade, stream):
    learning_areas = Strand.objects.filter(school_id=school_id).values('subject').distinct()
    dashboard_data = []

    for area in learning_areas:
        subject_name = area['subject']
        subject_strands = Strand.objects.filter(school_id=school_id, subject=subject_name)
        area_substrands = SubStrand.objects.filter(strand__in=subject_strands)
        total_substrands_count = area_substrands.count()

        if not area_substrands.exists():
            continue

        all_marks_in_area = SubStrandMark.objects.filter(sub_strand__in=area_substrands)
        if selected_year:
            all_marks_in_area = all_marks_in_area.filter(year=selected_year)
        if selected_term:
            all_marks_in_area = all_marks_in_area.filter(term=selected_term)
        if grade:
            all_marks_in_area = all_marks_in_area.filter(student__grade=grade)
        if stream:
            all_marks_in_area = all_marks_in_area.filter(student__stream=stream)

        if not all_marks_in_area.exists():
            dashboard_data.append({
                'name': subject_name,
                'avg_level_area': 0,
                'avg_score': 0,
                'total_students': 0,
                'level_distribution': {},
                'total_substrands': total_substrands_count
            })
            continue

        area_aggregate = all_marks_in_area.aggregate(
            avg_level=Avg('level'),
            avg_score=Avg('score'),
            total_students=Count('student', distinct=True)
        )
        level_distribution_raw = all_marks_in_area.values('level').annotate(count=Count('level'))
        distribution_map = {LEVEL_NAMES.get(item['level']): item['count'] for item in level_distribution_raw if item['level'] in LEVEL_NAMES}
        final_distribution = {label: distribution_map.get(label, 0) for _, label in LEVEL_NAMES.items()}

        dashboard_data.append({
            'name': subject_name,
            'avg_level_area': round(area_aggregate['avg_level'] or 0, 2),
            'avg_score': round(area_aggregate['avg_score'] or 0, 2),
            'total_students': area_aggregate['total_students'],
            'level_distribution': final_distribution,
            'total_substrands': total_substrands_count,
        })
    return dashboard_data


class CBCDashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        year_str = request.GET.get('year', '')
        year = datetime.now().year
        if year_str:
            try:
                year = int(year_str)
            except ValueError:
                pass

        term = request.GET.get('term', '')
        grade = request.GET.get('grade', '')
        stream = request.GET.get('stream', '')

        learning_areas_data = get_dashboard_comparison_data(school_id, term, year, grade, stream)

        marks_qs = SubStrandMark.objects.filter(student__school_id=school_id)
        if year:
            marks_qs = marks_qs.filter(year=year)
        if term:
            marks_qs = marks_qs.filter(term=term)

        grades = list(GradeStreamConfig.objects.filter(school_id=school_id).values_list('grade', flat=True).distinct())
        grades_to_process = [grade] if grade else grades

        top_students_per_grade = {}
        pie_data = []
        line_data = []
        grade_distribution_data = []

        for g in grades_to_process:
            student_filter = {'school_id': school_id, 'grade': g}
            if stream:
                student_filter['stream'] = stream

            reg_nos = StudentInfo.objects.filter(**student_filter).values_list('registration_no', flat=True)
            grade_marks = (
                marks_qs.filter(student__registration_no__in=reg_nos)
                .values('student__registration_no')
                .annotate(avg_score=Avg('score'))
                .order_by('-avg_score')[:3]
            )

            students_list = []
            for m in grade_marks:
                student = StudentInfo.objects.filter(school_id=school_id, registration_no=m['student__registration_no']).first()
                if student:
                    students_list.append({
                        'name': f"{student.first_name} {student.surname}",
                        'stream': student.stream,
                        'avg_score': round(m['avg_score'], 2),
                    })
            top_students_per_grade[g] = students_list

            pie_data.append(len(reg_nos))
            avg_score = marks_qs.filter(student__registration_no__in=reg_nos).aggregate(avg=Avg('score'))['avg'] or 0
            line_data.append(round(avg_score, 2))

            dist_raw = marks_qs.filter(student__registration_no__in=reg_nos).values('level').annotate(count=Count('level'))
            dist_map = {LEVEL_NAMES.get(item['level']): item['count'] for item in dist_raw if item['level'] in LEVEL_NAMES}
            grade_distribution_data.append({
                'EE': dist_map.get('Exceeding Expectations', 0),
                'ME': dist_map.get('Meeting Expectation', 0),
                'AE': dist_map.get('Approaching Expectation', 0),
                'BE': dist_map.get('Below Expectation', 0),
            })

        return Response({
            'learning_areas': learning_areas_data,
            'top_students': top_students_per_grade,
            'pie_chart': {'labels': grades_to_process, 'data': pie_data},
            'line_chart': {'labels': grades_to_process, 'data': line_data},
            'grade_distributions': grade_distribution_data
        })


class CBCStudentPerformanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        grade = request.GET.get('grade', '')
        stream = request.GET.get('stream', '')
        year = request.GET.get('year', '')
        term = request.GET.get('term', '')

        student_filter = Q(school_id=school_id)
        if grade:
            student_filter &= Q(grade=grade)
        if stream:
            student_filter &= Q(stream=stream)

        students = StudentInfo.objects.filter(student_filter)
        results = []
        for student in students:
            marks = SubStrandMark.objects.filter(student=student)
            if year:
                marks = marks.filter(year=year)
            if term:
                marks = marks.filter(term=term)

            agg = marks.aggregate(avg_level=Avg('level'), avg_score=Avg('score'))
            level_data = get_cbc_level_and_remark(agg['avg_level'])

            results.append({
                'registration_no': student.registration_no,
                'name': f"{student.first_name} {student.surname}",
                'grade': student.grade,
                'stream': student.stream,
                'avg_score': round(agg['avg_score'] or 0, 2),
                'avg_level': round(agg['avg_level'] or 0, 1),
                'cbc_level': level_data['level'],
                'remark': level_data['remark']
            })
        return Response(results)


class CBCStudentStrandsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, reg_no):
        school_id = request.user.school_id
        student = get_object_or_404(StudentInfo, school_id=school_id, registration_no=reg_no)
        year = request.GET.get('year', '')
        term = request.GET.get('term', '')

        marks = SubStrandMark.objects.filter(student=student).select_related('sub_strand', 'sub_strand__strand')
        if year:
            marks = marks.filter(year=year)
        if term:
            marks = marks.filter(term=term)

        results = [{
            'id': mark.id,
            'subject': mark.sub_strand.strand.subject,
            'strand': mark.sub_strand.strand.name,
            'sub_strand': mark.sub_strand.name,
            'score': mark.score,
            'level': mark.level,
            'level_name': LEVEL_NAMES.get(mark.level, 'Unknown'),
            'term': mark.term,
            'year': mark.year,
            'remark': mark.remark
        } for mark in marks]

        return Response({
            'student_name': f"{student.first_name} {student.surname}",
            'registration_no': student.registration_no,
            'grade': student.grade,
            'stream': student.stream,
            'marks': results
        })


class CBCStudentCompetenciesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, reg_no):
        school_id = request.user.school_id
        student = get_object_or_404(StudentInfo, school_id=school_id, registration_no=reg_no)
        year = request.GET.get('year', '')
        term = request.GET.get('term', '')

        competencies = LearnerCompetency.objects.filter(student=student)
        if year:
            competencies = competencies.filter(year=year)
        if term:
            competencies = competencies.filter(term=term)

        overall_averages = competencies.values('competency').annotate(avg_level=Avg('level')).order_by('competency')
        subject_competencies = competencies.values('subject', 'competency').annotate(avg_level=Avg('level')).order_by('subject', 'competency')

        subject_data = {}
        for item in subject_competencies:
            subj = item['subject']
            if subj not in subject_data:
                subject_data[subj] = []
            level_rounded = round(item['avg_level'])
            subject_data[subj].append({
                'competency': item['competency'],
                'avg_level': round(item['avg_level'], 2),
                'level_name': LEVEL_NAMES.get(level_rounded, 'Unknown')
            })

        overall_list = [{
            'competency': item['competency'],
            'avg_level': round(item['avg_level'], 2),
            'level_name': LEVEL_NAMES.get(round(item['avg_level']), 'Unknown')
        } for item in overall_averages]

        return Response({
            'student_name': f"{student.first_name} {student.surname}",
            'registration_no': student.registration_no,
            'overall_competencies': overall_list,
            'subject_competencies': subject_data
        })


class CBCGradeCompetenciesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        school_id = request.user.school_id
        grade = request.GET.get('grade', '')
        stream = request.GET.get('stream', '')
        year = request.GET.get('year', '')
        term = request.GET.get('term', '')

        if not grade:
            return Response({"error": "Grade parameter is required"}, status=400)

        competencies = LearnerCompetency.objects.filter(school_id=school_id, student__grade=grade)
        if stream:
            competencies = competencies.filter(student__stream=stream)
        if year:
            competencies = competencies.filter(year=year)
        if term:
            competencies = competencies.filter(term=term)

        analysis = competencies.values('competency', 'level').annotate(
            student_count=Count('student', distinct=True)
        ).order_by('competency', '-level')

        result = {}
        for item in analysis:
            comp = item['competency']
            lvl = item['level']
            count = item['student_count']
            if comp not in result:
                result[comp] = {
                    'Exceeding Expectations': 0,
                    'Meeting Expectation': 0,
                    'Approaching Expectation': 0,
                    'Below Expectation': 0
                }
            level_name = LEVEL_NAMES.get(lvl)
            if level_name in result[comp]:
                result[comp][level_name] += count

        formatted_result = [
            {'competency': comp, 'distributions': distributions}
            for comp, distributions in result.items()
        ]

        return Response({'grade': grade, 'stream': stream, 'analysis': formatted_result})