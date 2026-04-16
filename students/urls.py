from django.urls import path
from core.views.auth_views import *
from core.views.dashboard_views import *

from core.views.pdf_views import *





# ── Class-Based Views from students_api ───────────────────────────────────────
from .views.students_api import (
    ConfigRegNoView,
    NextRegistrationNumberView,
    StudentListView,
    StudentDetailView,
    StudentStatsView,
    
    StudentSearchView,
    GradeStreamView,
    GradesListView,
    StreamsListView,
    GradeStreamMappingView,
    StudentFeesView,
    MonthlyFeesView,
    RecordPaymentView,
    FeeRecordsView,
    UpdateFeeStatusView,
    FeesByGradeView,
    StudentAttendanceView,
    StudentAttendanceByGradeView,
    StudentMonthlyAttendanceView,
    AllStudentsAttendanceView,
    SendAttendanceNotificationsView,
    AttendanceSettingsView,
    StudentAcademicsView,
    AcademicsByGradeView,
    TopStudentsView,
    GenerateReportView,
    LeavesListView,
    ApplyLeaveView,
    EligibleLeaveStudentsView,
    ApplyBulkLeaveView,
    UpdateLeaveStatusView,
    UpdateLeaveReturnDateView,
    LeavesSummaryByGradeView,
    CBCDashboardStatsView,
    CBCStudentPerformanceView,
    CBCStudentStrandsView,
    CBCStudentCompetenciesView,
    CBCGradeCompetenciesView,
)



from .views.student_portal_views import (
    StudentPortalDashboardAPIView,
    StudentPortalAttendanceAPIView,
    StudentPortalFeesAPIView,
    StudentPortalAcademicsAPIView,
    StudentPortalLeaveAPIView,
    StudentResourceAPIView,
    StudentNoteAPIView,
    StudentAllNotesAPIView,
    StudentResourceTrackAPIView,
    StudentSubjectStrandsAPIView,
    StudentSubjectCompetenciesAPIView,
)

from .views.parent_portal_views import (
    ParentPortalDashboardAPIView,
    ParentPortalAttendanceAPIView,
    ParentPortalFeesAPIView,
    ParentPortalAcademicsAPIView,
    ParentPortalLeaveAPIView,
)

from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(['GET'])
def students_root(request):
    return Response({"message": "students is running"})


urlpatterns = [
    # ── Parent Portal ──────────────────────────────────────────────────────────
    path("parent-portal/dashboard/",   ParentPortalDashboardAPIView.as_view(),   name="api-parent-portal-dashboard"),
    path("parent-portal/attendance/",  ParentPortalAttendanceAPIView.as_view(),  name="api-parent-portal-attendance"),
    path("parent-portal/fees/",        ParentPortalFeesAPIView.as_view(),        name="api-parent-portal-fees"),
    path("parent-portal/academics/",   ParentPortalAcademicsAPIView.as_view(),   name="api-parent-portal-academics"),
    path("parent-portal/leave/",       ParentPortalLeaveAPIView.as_view(),       name="api-parent-portal-leaves"),

    # ── Root ───────────────────────────────────────────────────────────────────
    path("", students_root, name="students-root"),

    # ── Auth ───────────────────────────────────────────────────────────────────
    path('auth/login/',    login,             name='login'),
    path('auth/register/', register,          name='register'),
    path('auth/logout/',   logout,            name='logout'),
    path('auth/me/',       get_current_user,  name='current-user'),
    path('auth/schools/',  get_schools,       name='schools'),
    path('auth/change-password/', change_password, name='change-password'),
    path('auth/change-username/', change_username, name='change-username'),


    # ── Dashboard ──────────────────────────────────────────────────────────────
    path('dashboard/',             dashboard,                         name='dashboard'),
    path('dashboard/monthly/',     MonthlyFeesView.as_view(),         name='dashboard-monthly'),
    path('dashboard/activities/',  RecentActivitiesView.as_view(),    name='recent-activities'),

    # ── Student Registration Config ────────────────────────────────────────────
    path('students/config-reg-no/',      ConfigRegNoView.as_view(),           name='config-reg-no'),
    path('students/next-registration/',  NextRegistrationNumberView.as_view(), name='next-registration'),
    path('students/stats/',              StudentStatsView.as_view(),           name='students-stats'),
    path('students/search/',             StudentSearchView.as_view(),          name='students-search'),

    # ── Student CRUD ───────────────────────────────────────────────────────────
    path('students/',          StudentListView.as_view(),   name='students-list'),
    path('students/<str:reg_no>/', StudentDetailView.as_view(), name='student-detail'),

    # ── Student Attendance ────────────────────────────────────────────────────
    path('students/attendance/monthly/', StudentMonthlyAttendanceView.as_view(), name='student-attendance-monthly'),

    # ── Grades & Streams ──────────────────────────────────────────────────────
    path('grades/',         GradesListView.as_view(),       name='grades-list'),
    path('streams/',        StreamsListView.as_view(),      name='streams-list'),
    path('grades-streams/', GradeStreamMappingView.as_view(), name='grade-stream-mapping'),
    path('gradestreams/',            GradeStreamView.as_view(), name='gradestreams-list'),
    path('gradestreams/<int:id>/',   GradeStreamView.as_view(), name='gradestreams-detail'),

    # ── Fees ──────────────────────────────────────────────────────────────────
    path('fees/monthly/',               MonthlyFeesView.as_view(),      name='monthly-fees'),
    path('fees/record/',                RecordPaymentView.as_view(),    name='record-payment'),
    path('fees/by-grade/',              FeesByGradeView.as_view(),      name='fees-by-grade'),
    path('fees/',                       FeeRecordsView.as_view(),       name='get-fee-records'),
    path('fees/<int:fee_id>/update-status/',   UpdateFeeStatusView.as_view(),  name='update-fee-status'),
    path('fees/<int:fee_id>/receipt/',  print_fee_reciept,              name='print-fee-receipt'),
    path('fees/generate-all-fee-receipts/',           print_all_fee_reciepts,                name='generate-all-fee-receipts'),


    # ── Reports ───────────────────────────────────────────────────────────────
    path('reports/generate_fee_report/',    generate_fee_report,          name='generate_fee_report'),
    path('reports/generate_fee_records/',   generate_fee_records_report,  name='generate_fee_records_report'),
    path('reports/fees/csv/',               GenerateReportView.as_view(), name='generate-report'),
    path('reports/fee_collection_summary_report/', fee_collection_summary_report, name='fee-collection-summary-report'),
    path('reports/school-performance/',     school_performance_summary,   name='school-performance-summary'),
    path('reports/class-grade-analysis/',   class_grade_analysis_report,  name='class-grade-analysis'),
    path('reports/subject-performance/',    subject_performance_report,   name='subject-performance-report'),
    path('reports/student-ranking/',        student_ranking_report,       name='student-ranking-report'),
    path('reports/attendance-summary/',     attendance_summary_report,    name='attendance-summary-report'),
    path('reports/leave-analysis/',         leave_analysis_report,        name='leave-analysis-report'),
    path('reports/competency-heatmap/',     competency_heatmap_report,    name='competency-heatmap-report'),

    # ── Attendance ────────────────────────────────────────────────────────────
    path('attendance/by-grade/',       StudentAttendanceByGradeView.as_view(),     name='attendance-by-grade'),
    path('attendance/all/',            AllStudentsAttendanceView.as_view(),         name='attendance-all'),
    path('attendance/notify/',         SendAttendanceNotificationsView.as_view(),   name='attendance-notify'),
    path('attendance/settings/',       AttendanceSettingsView.as_view(),            name='attendance-settings'),
    path('attendance/daily-summary/', AttendanceDailySummaryView.as_view(), name='attendance-daily-summary'),
    # ── PDF / Print ───────────────────────────────────────────────────────────
    path('reports/print_attendance_sheet/', print_attendance_sheet, name='print-attendance-sheet'),

    # ── Leaves ────────────────────────────────────────────────────────────────
    path('leaves/',                          LeavesListView.as_view(),           name='leaves-list'),
    path('leaves/apply/',                    ApplyLeaveView.as_view(),           name='apply-leave'),
    path('leaves/bulk/eligible-students/',   EligibleLeaveStudentsView.as_view(), name='eligible-leave-students'),
    path('leaves/bulk/apply/',               ApplyBulkLeaveView.as_view(),       name='apply-bulk-leave'),
    path('leaves/summary/by-grade/',         LeavesSummaryByGradeView.as_view(), name='leaves-summary-by-grade'),
    path('leaves/reports/generate/',         generate_leave_report,              name='generate-leave-report'),
    path('leaves/<int:leave_id>/status/',    UpdateLeaveStatusView.as_view(),    name='update-leave-status'),
    path('leaves/<int:leave_id>/return/',    UpdateLeaveReturnDateView.as_view(), name='update-leave-return-date'),
    path('leaves/<int:leave_id>/receipt/',   print_leave_receipt,                name='print-leave-receipt'),
    path('leaves/reports/generate-all-receipts/', print_leave_receipts,           name='generate-all-leave-receipts'),

    # ── Academics ─────────────────────────────────────────────────────────────
    path('academics/by-grade/',                            AcademicsByGradeView.as_view(),       name='academics-by-grade'),
    path('academics/top-students/',                        TopStudentsView.as_view(),             name='top-students'),
    path('academics/cbc/dashboard/',                       CBCDashboardStatsView.as_view(),       name='cbc-dashboard-stats'),
    path('academics/cbc/performance/',                     CBCStudentPerformanceView.as_view(),   name='cbc-student-performance'),
    path('academics/cbc/student/<str:reg_no>/strands/',    CBCStudentStrandsView.as_view(),       name='cbc-student-strands'),
    path('academics/cbc/student/<str:reg_no>/competencies/', CBCStudentCompetenciesView.as_view(), name='cbc-student-competencies'),
    path('academics/cbc/grade-competencies/',              CBCGradeCompetenciesView.as_view(),    name='cbc-grade-competencies'),
    path('academics/generate-report-forms/',               print_report_forms,                    name='generate-report-forms'),
    path('academics/generate-result-papers/',              generate_result_papers,                name='generate-result-papers'),
    path('academics/generate-academic-report/',            generate_academic_report,              name='generate-academic-report'),
    path('academics/generate-summative-report-forms/',     print_summative_report_forms,          name='generate-summative-report-forms'),
    path('academics/summative-individual-report/',         print_individual_summative_report_form, name='summative-individual-report'),
    
    # ── Teachers ──────────────────────────────────────────────────────────────
    

    # ── Student Detail Sub-routes ─────────────────────────────────────────────
    path('students/<str:reg_no>/fees/',        StudentFeesView.as_view(),      name='student-fees'),
    path('students/<str:reg_no>/attendance/',  StudentAttendanceView.as_view(), name='student-attendance'),
    path('students/<str:reg_no>/academics/',   StudentAcademicsView.as_view(), name='student-academics'),

    
    # ── Student Portal ────────────────────────────────────────────────────────
    path("student-portal/dashboard/",                    StudentPortalDashboardAPIView.as_view(),       name="api-student-portal-dashboard"),
    path("student-portal/attendance/",                   StudentPortalAttendanceAPIView.as_view(),      name="api-student-portal-attendance"),
    path("student-portal/fees/",                         StudentPortalFeesAPIView.as_view(),            name="api-student-portal-fees"),
    path("student-portal/academics/",                    StudentPortalAcademicsAPIView.as_view(),       name="api-student-portal-academics"),
    path("student-portal/academics/report-form/",        print_individual_report_form,                  name="api-student-portal-report-form"),
    path("student-portal/leave/",                        StudentPortalLeaveAPIView.as_view(),           name="api-student-portal-leaves"),
    path("student-portal/strands/",                      StudentSubjectStrandsAPIView.as_view(),        name="api-student-strands"),
    path("student-portal/academics/competencies/",       StudentSubjectCompetenciesAPIView.as_view(),   name="api-student-subject-competencies"),
    path("student-portal/resources/",                    StudentResourceAPIView.as_view(),              name="api-student-resources"),
    path("student-portal/resources/<int:resource_id>/track/", StudentResourceTrackAPIView.as_view(),   name="api-student-resource-track"),
    path("student-portal/notes/",                        StudentAllNotesAPIView.as_view(),              name="api-student-all-notes"),
    path("student-portal/resources/<int:resource_id>/note/", StudentNoteAPIView.as_view(),             name="api-student-resource-note"),
]