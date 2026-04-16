from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    MasterSchool, Users, RegConfig, TeacherInfo, TeacherAttendance, TeachersRole,
    TeachingProgress, TeacherLeave, Resource, LearningArea, StudentInfo,
    LearningAreaMark, Fee, StudentAttendance, Strand, SubStrand, SubStrandMark,
    LearnerCompetency, GradeStreamConfig, GradeFeeConfig, LeaveManagement,
    StudentNote, LearningLog, ContactMessage, Announcement, Reviews
)

# ---------------- User & Auth ----------------
@admin.register(Users)
class UsersAdmin(admin.ModelAdmin):
    list_display = ('username', 'school', 'role', 'is_staff', 'is_active')
    list_filter = ('role', 'school', 'is_staff', 'is_active')
    search_fields = ('username', 'email')
    ordering = ('username',)

# ---------------- School Core ----------------
@admin.register(MasterSchool)
class MasterSchoolAdmin(admin.ModelAdmin):
    list_display = ('school_name', 'email_address', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('school_name', 'email_address')

@admin.register(RegConfig)
class RegConfigAdmin(admin.ModelAdmin):
    list_display = ('school', 'target_type', 'reg_format')
    list_filter = ('school', 'target_type')

@admin.register(GradeStreamConfig)
class GradeStreamConfigAdmin(admin.ModelAdmin):
    list_display = ('school', 'grade', 'stream')
    list_filter = ('school', 'grade')

@admin.register(GradeFeeConfig)
class GradeFeeConfigAdmin(admin.ModelAdmin):
    list_display = ('school', 'grade', 'expected_fee', 'term')
    list_filter = ('school', 'term')

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'subject', 'created_at')
    search_fields = ('name', 'email', 'subject')

# ---------------- Teacher Management ----------------
@admin.register(TeacherInfo)
class TeacherInfoAdmin(admin.ModelAdmin):
    list_display = ('registration_no', 'school', 'first_name', 'surname', 'phone')
    list_filter = ('school', 'gender')
    search_fields = ('registration_no', 'first_name', 'surname', 'phone')

@admin.register(TeacherAttendance)
class TeacherAttendanceAdmin(admin.ModelAdmin):
    list_display = ('registration_no', 'school', 'date_of_attendance', 'status', 'time_in')
    list_filter = ('school', 'status', 'date_of_attendance')

@admin.register(TeachersRole)
class TeachersRoleAdmin(admin.ModelAdmin):
    list_display = ('registration_no', 'school', 'type_of_teacher', 'grade', 'stream')
    list_filter = ('school', 'type_of_teacher', 'grade')

@admin.register(TeachingProgress)
class TeachingProgressAdmin(admin.ModelAdmin):
    list_display = ('registration_no', 'school', 'grade', 'subject', 'topic', 'status')
    list_filter = ('school', 'grade', 'status')

@admin.register(TeacherLeave)
class TeacherLeaveAdmin(admin.ModelAdmin):
    list_display = ('teacher', 'leave_type', 'start_date', 'end_date', 'status')
    list_filter = ('status', 'leave_type', 'school')

# ---------------- Student Management & Finance ----------------
@admin.register(StudentInfo)
class StudentInfoAdmin(admin.ModelAdmin):
    list_display = ('registration_no', 'school', 'first_name', 'surname', 'grade', 'stream')
    list_filter = ('school', 'grade', 'stream', 'gender')
    search_fields = ('registration_no', 'first_name', 'surname')

@admin.register(StudentAttendance)
class StudentAttendanceAdmin(admin.ModelAdmin):
    list_display = ('registration_no', 'school', 'date_of_attendance', 'status')
    list_filter = ('school', 'status', 'date_of_attendance')

@admin.register(LeaveManagement)
class StudentLeaveAdmin(admin.ModelAdmin):
    list_display = ('student', 'school', 'reason', 'start_date', 'return_date', 'status')
    def start_date(self, obj): return obj.date_of_leave
    list_filter = ('school', 'status')

@admin.register(Fee)
class FeeAdmin(admin.ModelAdmin):
    list_display = ('registration_no', 'school', 'amount', 'date_of_payment', 'status')
    list_filter = ('school', 'status', 'term')
    search_fields = ('transaction_code', 'registration_no__registration_no')

# ---------------- Academics (CBC & 8-4-4) ----------------
@admin.register(LearningArea)
class LearningAreaAdmin(admin.ModelAdmin):
    list_display = ('name', 'grade_level', 'school')
    list_filter = ('school', 'grade_level')

@admin.register(LearningAreaMark)
class LearningAreaMarkAdmin(admin.ModelAdmin):
    list_display = ('student', 'learning_area', 'exam_type', 'marks', 'term', 'year')
    list_filter = ('school', 'exam_type', 'term', 'year')

@admin.register(Strand)
class StrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'subject', 'grade', 'school')
    list_filter = ('school', 'grade', 'subject')

@admin.register(SubStrand)
class SubStrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'strand')
    list_filter = ('strand__subject', 'strand__grade')

@admin.register(SubStrandMark)
class SubStrandMarkAdmin(admin.ModelAdmin):
    list_display = ('student', 'sub_strand', 'score', 'term', 'year')
    list_filter = ('term', 'year')

@admin.register(LearnerCompetency)
class LearnerCompetencyAdmin(admin.ModelAdmin):
    list_display = ('student', 'competency', 'level', 'term', 'year')
    list_filter = ('school', 'competency', 'level')

@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ('title', 'resource_type', 'subject', 'grade', 'term')
    list_filter = ('school', 'resource_type', 'subject')

@admin.register(StudentNote)
class StudentNoteAdmin(admin.ModelAdmin):
    list_display = ('student', 'resource', 'updated_at')

@admin.register(LearningLog)
class LearningLogAdmin(admin.ModelAdmin):
    list_display = ('student', 'resource', 'progress', 'completed')

# ---------------- Communication ----------------
@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'school', 'target_audience', 'created_at')
    list_filter = ('school', 'target_audience')

@admin.register(Reviews)
class ReviewsAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'school', 'rating', 'is_approved', 'created_at')
    list_filter = ('school', 'is_approved', 'rating')
    actions = ['approve_reviews']

    def approve_reviews(self, request, queryset):
        queryset.update(is_approved=True)
    approve_reviews.short_description = "Approve selected reviews"
