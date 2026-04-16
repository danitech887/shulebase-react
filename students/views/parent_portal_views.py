from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db.models import Sum, Avg, Q
from decimal import Decimal
from datetime import datetime

from core.models import StudentInfo, StudentAttendance, Fee, LeaveManagement, SubStrandMark, GradeFeeConfig
from core.serializers import StudentInfoSerializer, LeaveManagementSerializer, StrandSerializer, StudentAttendanceSerializer, SubStrandMarkSerializer, FeeRecordSerializer

class ParentBaseView(APIView):
    """
    Base helper class to ensure parents only access their own children.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_parent_context(self, request):
        school_id = request.user.school_id
        phone = request.user.username
        
        students = StudentInfo.objects.filter(school_id=school_id, phone=phone)
        reg_no = request.query_params.get('student_id')
        
        selected_student = students.filter(registration_no=reg_no).first() or students.first()
            
        return school_id, students, selected_student

# --- DASHBOARD VIEW ---
class ParentPortalDashboardAPIView(ParentBaseView):
    def get(self, request):
        school_id, students, student = self.get_parent_context(request)
        if not student:
            return Response({"error": "No students linked"}, status=404)

        # Attendance calculation
        attendance = StudentAttendance.objects.filter(registration_no=student.registration_no)
        total_days = attendance.count()
        present = attendance.filter(status='Present').count()
        
        # Fee Summary
        fee_paid = Fee.objects.filter(registration_no=student, status='Confirmed').aggregate(Sum('amount'))['amount__sum'] or 0

        # Get expected fee for the student's grade
        expected_fee = Decimal(0)
        try:
            # Use the student's grade to look up the Grade object
            grade_obj = GradeFeeConfig.objects.get(school_id=school_id, grade=student.grade)
            expected_fee = grade_obj.expected_fee
        except GradeFeeConfig.DoesNotExist:
            # If no grade object is found, fee balance will be calculated against 0
            pass

        data = {
            "children": StudentInfoSerializer(students, many=True).data,
            "selected_child": StudentInfoSerializer(student).data,
            "stats": {
                "attendance_rate": (present / total_days * 100) if total_days > 0 else 0,
                "fee_balance": float(expected_fee - Decimal(fee_paid)),
                "pending_leaves": LeaveManagement.objects.filter(student=student, status='Pending').count()
            }
        }
        return Response(data)


# --- FEES MANAGEMENT ---

from core.views.integrations import initiate_stk_push

class ParentPortalFeesAPIView(ParentBaseView):
    def get(self, request):
        school_id, _, student = self.get_parent_context(request)
        payments = Fee.objects.filter(registration_no=student).order_by('-date_of_payment')
        
        return Response({
            "confirmed": FeeRecordSerializer(payments.filter(status='Confirmed'), many=True).data,
            "pending": FeeRecordSerializer(payments.exclude(status='Confirmed'), many=True).data,
            "summary": {
                "total_paid": payments.filter(status='Confirmed').aggregate(Sum('amount'))['amount__sum'] or 0
            }
        })

    def post(self, request):
        """
        Allows a parent to report a fee payment by providing transaction details.
        Creates a 'Pending' fee record for admin confirmation.
        """
        school_id, _, student = self.get_parent_context(request)

        data = request.data.copy()
        data['school'] = school_id
        data['registration_no'] = student.pk if student else None

        # The serializer will validate required fields like amount, transaction_code, etc.
        serializer = FeeRecordSerializer(data=data)
        if serializer.is_valid():
            tx_code = serializer.validated_data.get('transaction_code', '').strip()

            # Ensure transaction code is unique for the school
            if tx_code and Fee.objects.filter(transaction_code=tx_code, school_id=school_id).exists():
                return Response({"error": "This transaction code has already been reported."}, status=status.HTTP_400_BAD_REQUEST)

            # Save the new fee record as 'Pending' for admin review
            serializer.save(registration_no=student, school_id=school_id, status='Pending', year=datetime.now().year)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # --- M-PESA INTEGRATION ---
        # try:
        #     # 1. Trigger the STK Push via Daraja
        #     mpesa_response = initiate_stk_push(phone, amount)
            
        #     # 2. Check if M-Pesa API accepted the request
        #     if mpesa_response.get('ResponseCode') == '0':
        #         checkout_id = mpesa_response.get('CheckoutRequestID')
                
        #         # 3. Create the PENDING Fee record
        #         # We save the CheckoutRequestID so the callback can find this specific record later
        #         Fee.objects.create(
        #             registration_no=student,
        #             school_id=school_id,
        #             amount=amount,
        #             checkout_id=checkout_id, # REQUIRED: Add this field to your Fee model
        #             status='Pending',
        #             mode_of_payment='M-Pesa',
        #             term=term,
        #             date_of_payment=datetime.now().date(),
        #             year=datetime.now().year
        #         )
                
        #         return Response({
        #             "message": "STK Push initiated. Check your phone to enter PIN.",
        #             "checkout_id": checkout_id
        #         }, status=status.HTTP_201_CREATED)
            
        #     else:
        #         # Handle M-Pesa rejection (e.g. invalid phone number)
        #         error_msg = mpesa_response.get('CustomerMessage', "M-Pesa service error")
        #         return Response({"error": error_msg}, status=400)

        # except Exception as e:
        #     return Response({"error": f"Payment trigger failed: {str(e)}"}, status=500)

    def put(self, request):
        # ... keep your existing PUT logic here for rejected payments ...
        school_id, _, student = self.get_parent_context(request)
        fee_id = request.data.get('id')
        if not fee_id:
            return Response({"error": "Fee ID is required"}, status=400)
        
        try:
            fee = Fee.objects.get(id=fee_id, registration_no=student, school_id=school_id)
        except Fee.DoesNotExist:
            return Response({"error": "Fee record not found"}, status=404)
        
        if fee.status != 'Rejected':
            return Response({"error": "Only rejected payments can be edited"}, status=400)

        serializer = FeeRecordSerializer(fee, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save(status='Pending')
            return Response(serializer.data)
        return Response(serializer.errors, status=400)


# --- ATTENDANCE OVERVIEW ---
class ParentPortalAttendanceAPIView(ParentBaseView):
    def get(self, request):
        _, _, student = self.get_parent_context(request)
        attendance_records = StudentAttendance.objects.filter(registration_no=student).order_by('-date_of_attendance')
        
        return Response(StudentAttendanceSerializer(attendance_records, many=True).data)
# --- LEAVE MANAGEMENT ---
class ParentPortalLeaveAPIView(ParentBaseView):
    def get(self, request):
        _, _, student = self.get_parent_context(request)
        leaves = LeaveManagement.objects.filter(registration_no=student).order_by('-date_of_leave')
        
        return Response({
            "pending": leaves.filter(status='Pending').values('id', 'reason', 'date_of_leave', 'return_date'),
            "approved": leaves.filter(status='Approved').values('id', 'reason', 'date_of_leave', 'return_date'),
            "rejected": leaves.filter(status='Rejected').values('id', 'reason', 'date_of_leave', 'return_date'),
        })
    def post(self, request):
        school_id, _, student = self.get_parent_context(request)
        
        data = request.data.copy()
        data['school'] = school_id
        data['registration_no'] = student.pk if student else None
        
        serializer = LeaveManagementSerializer(data=data)
        
        if serializer.is_valid():
            serializer.save(
                registration_no=student, 
                school_id=school_id, 
                status='Pending',
                year=datetime.now().year
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
# --- ACADEMICS (CBC) ---
class ParentPortalAcademicsAPIView(ParentBaseView):
    def get(self, request):
        _, _, student = self.get_parent_context(request)
        term = request.query_params.get('term', 'Term 1')
        year = request.query_params.get('year', datetime.now().year)

        # Aggregating Subject Performance
        marks = SubStrandMark.objects.filter(student=student, term=term, year=year)
        subjects = marks.values('sub_strand__strand__subject').annotate(
            avg_score=Avg('score'),
            avg_level=Avg('level')
        )

        performance = []
        for s in subjects:
            level_data = self.get_cbc_rating(s['avg_level'])
            performance.append({
                "subject": s['sub_strand__strand__subject'],
                "score": round(s['avg_score'], 2),
                "rating": level_data['level'],
                "remark": level_data['remark']
            })

        return Response({
            "student": student.first_name,
            "term": term,
            "performance": performance
        })

    @staticmethod
    def get_cbc_rating(avg_level):
        if not avg_level: return {'level': 'N/A', 'remark': 'No Data'}
        if avg_level >= 3.5: return {'level': 'EE', 'remark': 'Exceeding Expectations'}
        if avg_level >= 2.5: return {'level': 'ME', 'remark': 'Meeting Expectations'}
        if avg_level >= 1.5: return {'level': 'AE', 'remark': 'Approaching Expectations'}
        return {'level': 'BE', 'remark': 'Below Expectations'} 