

from django.urls import path
from .views.teachers_views import*

from .views.teacher_portal_views import *
from core.views.pdf_views import print_subject_aggregated_report, print_attendance_report

urlpatterns = [
    # ── Automated Reports ─────────────────────────────────────────────────────
    path("teacher-portal/reports/subject-aggregated/",                         print_subject_aggregated_report,         name="api-report-subject-aggregated"),
    path("teacher-portal/reports/attendance/",                                 print_attendance_report,                 name="api-report-attendance"),

    path('teachers/',
         TeacherListView.as_view(),
         name='teachers-list'),
 
    path('teachers/stats/',
         TeacherStatsView.as_view(),
         name='teacher-stats'),
 
    path('teachers/next-registration/',
         NextTeacherRegistrationView.as_view(),
         name='next-teacher-registration'),
 
    path('teachers/config-reg-no/',
         TeacherRegConfigView.as_view(),
         name='teacher-config-reg-no'),
 
    # ── Attendance ─────────────────────────────────────────────────
    path('teachers/attendance/records/',
         TeacherAttendanceRecordsView.as_view(),
         name='teacher-attendance-records'),
 
    path('teachers/attendance/monthly/',
         TeacherMonthlyAttendanceView.as_view(),
         name='teacher-monthly-attendance'),
 
    # ── Roles & Learning Areas ──────────────────────────────────────
    path('teachers/roles/',
         TeacherRolesView.as_view(),
         name='teacher-roles'),
 
    path('teachers/roles/<int:role_id>/',
         TeacherRoleDetailView.as_view(),
         name='teacher-role-detail'),
 
    path('teachers/learning-areas/',
         LearningAreasView.as_view(),
         name='learning-areas'),
 
    # ── Leave ───────────────────────────────────────────────────────
    path('teachers/leave/',
         TeacherLeaveListView.as_view(),
         name='teacher-leave-list'),
 
    path('teachers/leave/stats/',
         TeacherLeaveStatsView.as_view(),
         name='teacher-leave-stats'),
 
    path('teachers/leave/<int:leave_id>/',
         TeacherLeaveDetailView.as_view(),
         name='teacher-leave-detail'),
 
    # ── Detail (keep last — catches <str:reg_no>) ───────────────────
    path('teachers/<str:reg_no>/',
         TeacherDetailView.as_view(),
         name='teacher-detail'),



    # ── Teacher Portal ────────────────────────────────────────────────────────
    # ── Teacher Portal ────────────────────────────────────────────────────────
    path("teacher-portal/dashboard/",                                          DashboardAPIView.as_view(),              name="api-dashboard"),
    path("teacher-portal/account/",                                            TeacherAccountAPIView.as_view(),         name="api-teacher-account"),
    path("teacher-portal/attendance/",                                         AttendanceAPIView.as_view(),             name="api-attendance"),
    path("teacher-portal/strands/",                                            StrandListAPIView.as_view(),             name="api-strand-list"),
    path("teacher-portal/strands/<int:pk>/",                                   StrandDetailAPIView.as_view(),           name="api-strand-detail"),
    path("teacher-portal/strands/<int:strand_id>/sub-strands/<str:grade>/<str:stream>/",
                                                                               SubStrandListAPIView.as_view(),          name="api-substrand-list"),
    path("teacher-portal/sub-strands/<int:sub_strand_id>/",                    SubStrandDetailAPIView.as_view(),        name="api-substrand-detail"),
    path("teacher-portal/sub-strands/<int:sub_strand_id>/scores/<str:grade>/<str:stream>/",
                                                                               SubStrandScoresAPIView.as_view(),        name="api-substrand-scores"),
    path("teacher-portal/teaching-progress/",                                  TeachingProgressAPIView.as_view(),       name="api-teaching-progress"),
    path("teacher-portal/teaching-progress/<int:pk>/",                         TeachingProgressDetailAPIView.as_view(), name="api-teaching-progress-detail"),
    path("teacher-portal/learner-competencies/",                               LearnerCompetencyAPIView.as_view(),      name="api-learner-competencies"),
    path("teacher-portal/resources/",                                          ResourceListCreateAPIView.as_view(),     name="api-resources"),
    path("teacher-portal/resources/<int:pk>/progress/",                        ResourceProgressAPIView.as_view(),       name="api-resource-progress"),
    path("teacher-portal/learning-area-marks/",                                LearningAreaMarkAPIView.as_view(),       name="api-learning-area-marks"),

    # ── Automated Reports ─────────────────────────────────────────────────────
    path("teacher-portal/reports/subject-aggregated/",                         print_subject_aggregated_report,         name="api-report-subject-aggregated"),
    path("teacher-portal/reports/attendance/",                                 print_attendance_report,                 name="api-report-attendance"),

]