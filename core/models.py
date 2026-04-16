from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.conf import settings
# ---------------- Master School ----------------
class MasterSchool(models.Model):
    school_name = models.CharField(max_length=100)
    po_box = models.CharField(max_length=50)
    address = models.CharField(max_length=100)
    contact = models.CharField(max_length=20)
    email_address = models.EmailField()

    logo_path = models.ImageField(upload_to='school_logos/', blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    motto = models.CharField(max_length=255, blank=True, null=True)
    vision = models.TextField(blank=True, null=True)
    status_choices = ['Approved', 'Pending', 'Rejected']
    status = models.CharField(max_length=20, choices=[(status, status) for status in status_choices], default='Pending')

    class Meta:
        verbose_name = "Master School"
        db_table = 'school_info'
        
        

    def __str__(self):
        return self.school_name

# ---------------- Core Models ----------------

class UserManager(BaseUserManager):
    def create_user(self, username, email=None, password=None, **extra_fields):
        if not username:
            raise ValueError("The Username field is required")
        
        email = self.normalize_email(email)
        
        # --- FIX: Convert school ID to School Instance ---
        school_val = extra_fields.get('school')
        if school_val and not isinstance(school_val, MasterSchool):
            try:
                # This converts the "1" you typed in the terminal into the actual School object
                extra_fields['school'] = MasterSchool.objects.get(pk=school_val)
            except MasterSchool.DoesNotExist:
                raise ValueError(f"MasterSchool with id {school_val} does not exist.")
        # ------------------------------------------------
        
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        
        # Ensure role is set for superuser
        if "role" not in extra_fields:
            extra_fields["role"] = "SystemOwner"

        return self.create_user(username, email, password, **extra_fields)
class Users(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=50, unique=True)
    school = models.ForeignKey(MasterSchool, on_delete=models.CASCADE, related_name="users")
    school_name = models.CharField(max_length=100)
    role = models.CharField(max_length=30)
    registration_no = models.CharField(max_length=30, default="") 
    email = models.EmailField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    last_login = models.DateTimeField(null=True)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email", "role", "school"]

    objects = UserManager()

    class Meta:
        db_table = 'users'

    def __str__(self):
        return f"{self.username} ({self.role})"


class RegConfig(models.Model):
    school = models.ForeignKey(MasterSchool, on_delete=models.CASCADE, related_name="reg_configs")
    target_type = models.CharField(max_length=20)  # e.g., 'student'
    reg_format = models.CharField(max_length=50)  # e.g., "SCH-{{YEAR}}-{{MONTH}}-{{SEQ}}"

    class Meta:
        unique_together = ('school', 'target_type')
        db_table = 'reg_config'



class TeacherInfo(models.Model):
    registration_no = models.CharField(max_length=20, primary_key=True)
    school = models.ForeignKey(MasterSchool, on_delete=models.CASCADE, related_name="teachers")
    first_name = models.CharField(max_length=30)
    second_name = models.CharField(max_length=30, blank=True)
    surname = models.CharField(max_length=30)
    gender = models.CharField(max_length=10, choices=[('Male', 'Male'), ('Female', 'Female')])
    date_of_registration = models.DateField(blank=True, null=True, default=timezone.localdate)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    address = models.CharField(max_length=100, blank=True)

    

    def __str__(self):
        return f"{self.first_name} {self.second_name} {self.surname} ({self.registration_no})"

    class Meta:
        verbose_name = "Teacher Information"
        unique_together = ('school', 'registration_no')
        db_table = 'teacher_info'


class TeacherAttendance(models.Model):
    registration_no = models.ForeignKey(TeacherInfo, on_delete=models.CASCADE, db_column='registration_no')
    school = models.ForeignKey(MasterSchool, on_delete=models.CASCADE, related_name="teacher_attendance")
    date_of_attendance = models.DateField(blank=True, null=True)
    term = models.CharField(max_length=6, blank=True, null=True)
    year = models.IntegerField(blank=True, null=True, default=timezone.now().year)
    status = models.CharField(max_length=7, blank=True, null=True)
    time_in = models.TimeField(blank=True, null=True, default=timezone.now)

    

    class Meta:
        
        db_table = 'teacher_attendance'

class TeachersRole(models.Model):
    registration_no = models.ForeignKey(TeacherInfo, on_delete=models.CASCADE, db_column='registration_no')
    school = models.ForeignKey(MasterSchool, on_delete=models.CASCADE, related_name="teacher_roles")
    type_of_teacher = models.CharField(max_length=20, blank=True, null=True)
    grade = models.CharField(max_length=10, blank=True, null=True)
    stream = models.CharField(max_length=10, blank=True, null=True)
    subject = models.CharField(max_length=200, blank=True, null=True)

    

    class Meta:
        db_table = 'teacher_role'

class TeachingProgress(models.Model):
    registration_no = models.ForeignKey(TeacherInfo, on_delete=models.CASCADE, db_column='registration_no')
    school = models.ForeignKey(MasterSchool, on_delete=models.CASCADE, related_name="teaching_progress")
    grade = models.CharField(max_length=20)
    stream = models.CharField(max_length=20)
    subject = models.CharField(max_length=355, blank=True, null=True)
    no_of_topics = models.IntegerField(blank=True, null=True)
    topic = models.CharField(max_length=500, blank=True, null=True)
    sub_topic = models.CharField(max_length=500, blank=True, null=True)
    status = models.CharField(max_length=9, blank=True, null=True)
    date_of_teaching = models.DateTimeField(blank=True, null=True)
    date_finished = models.DateField(blank=True, null=True)

    

    class Meta:
        db_table = 'teaching_progress'

class TeacherLeave(models.Model):

    LEAVE_TYPE_CHOICES = [
        ('Annual',         'Annual Leave'),
        ('Sick',           'Sick Leave'),
        ('Maternity',      'Maternity Leave'),
        ('Paternity',      'Paternity Leave'),
        ('Compassionate',  'Compassionate Leave'),
        ('Unpaid',         'Unpaid Leave'),
        ('Other',          'Other'),
    ]

    STATUS_CHOICES = [
        ('Pending',   'Pending'),
        ('Approved',  'Approved'),
        ('Rejected',  'Rejected'),
        ('Cancelled', 'Cancelled'),
    ]

    school      = models.ForeignKey('MasterSchool', on_delete=models.CASCADE, related_name='teacher_leaves')
    teacher     = models.ForeignKey('TeacherInfo',  on_delete=models.CASCADE, related_name='leaves')

    leave_type  = models.CharField(max_length=20, choices=LEAVE_TYPE_CHOICES, default='Annual')
    reason      = models.TextField(blank=True)
    start_date  = models.DateField()
    end_date    = models.DateField()
    # computed / cached duration in days (optional — can be a property instead)
    duration    = models.PositiveIntegerField(default=0)

    status      = models.CharField(max_length=15, choices=STATUS_CHOICES, default='Pending')
    applied_on  = models.DateField(auto_now_add=True)

    # Admin review fields
    admin_note  = models.TextField(blank=True)
    reviewed_by = models.CharField(max_length=150, blank=True)
    reviewed_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-applied_on']
        verbose_name = 'Teacher Leave'
        db_table = 'teacher_leave'

    def save(self, *args, **kwargs):
        # Auto-calculate duration on save
        if self.start_date and self.end_date:
            delta = (self.end_date - self.start_date).days + 1
            self.duration = max(delta, 0)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.teacher} | {self.leave_type} | {self.status}"

class Resource(models.Model):
    TYPES = (('video', 'Video'), ('book', 'e-Book'))
    school = models.ForeignKey(MasterSchool, on_delete=models.CASCADE,default=1)
    
    title = models.CharField(max_length=255)
    subject = models.CharField(max_length=100)
    grade = models.CharField(max_length=10)  # e.g., 7 for Grade 7
    stream = models.CharField(max_length=19,default='A')
    term = models.CharField(max_length=10,choices=[('Term 1','Term 1'),('Term 2','Term 2'),('Term 3','Term 3')],default='Term 3')
    year = models.IntegerField(default=timezone.now().year)
    resource_type = models.CharField(max_length=10, choices=TYPES)
    url_or_file = models.CharField(max_length=500, help_text="YouTube ID or File URL")
    thumbnail = models.ImageField(upload_to='thumbs/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        db_table = 'learning_resources'


class LearningArea(models.Model):
    # The name of the subject (e.g., Mathematics, English, Home Science)
    name = models.CharField(max_length=100)
    
    # The code used for reports or IDs (e.g., MATH, ENG)
    
    # Link to the Grade level (Assuming you have a Grade model)
    # If you don't have a Grade model, use a CharField with choices
    grade_level = models.CharField(max_length=20) 

    # Track which school this belongs to in a multi-tenant system
    school = models.ForeignKey("MasterSchool",on_delete = models.CASCADE)

    # Optional: Category for grouping (e.g., Sciences, Humanities)
    category = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        # Prevent adding the same subject to the same grade twice
        unique_together = ('name', 'grade_level', 'school_id')
        db_table= 'learning_areas'

    def __str__(self):
        return f"{self.name} - {self.grade_level}"

    

def current_time_str():
    return timezone.now().strftime("%H:%M:%S")
 
def current_year_str():
    return timezone.now().strftime("%Y")





class StudentInfo(models.Model):
    registration_no = models.CharField(primary_key=True, max_length=20)
    school = models.ForeignKey(MasterSchool, on_delete=models.CASCADE, related_name="students")
    first_name = models.CharField(max_length=20)
    second_name = models.CharField(max_length=20)
    surname = models.CharField(max_length=20)
    gender = models.CharField(max_length=10)
    date_of_birth = models.DateField()
    date_of_registration = models.DateField(blank=True, null=True)
    parent_name = models.CharField(max_length=20, blank=True, null=True)
    grade = models.CharField(max_length=10)
    stream = models.CharField(max_length=10)
    phone = models.BigIntegerField()
    email = models.EmailField(max_length=50, blank=True, null=True)
    address = models.CharField(max_length=20)

    parent_portal_user = models.ForeignKey(Users, on_delete=models.SET_NULL, null=True, blank=True)


    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = timezone.now().date()
        return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))


    class Meta:
        verbose_name = "Student Information"
        unique_together = ('school', 'registration_no')
        db_table = 'student_info'

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.hashers import make_password

@receiver(post_save, sender=StudentInfo)
def manage_parent_account(sender, instance, created, **kwargs):
    if created:
        # Step A: Find or Create the Parent User
        parent_user, p_created = Users.objects.get_or_create(
            username=instance.phone,
            defaults={
                'role': 'Parent', 
                'password': make_password(str(instance.phone)),
                'school': instance.school
            }
        )
        
        # Step B: Link the parent to this student
        # We use .update() here to avoid triggering this signal again (infinite loop)
        StudentInfo.objects.filter(registration_no=instance.registration_no).update(parent_portal_user=parent_user)

class LearningAreaMark(models.Model):
    school = models.ForeignKey(MasterSchool, on_delete=models.CASCADE, related_name='learning_area_marks')
    student = models.ForeignKey(StudentInfo, on_delete=models.CASCADE, related_name='learning_area_marks')
    learning_area = models.ForeignKey(LearningArea, on_delete=models.CASCADE, related_name='marks')
    grade = models.CharField(max_length=20)
    stream = models.CharField(max_length=20)
    term = models.CharField(max_length=20)
    year = models.IntegerField(default=timezone.now().year)
    exam_type = models.CharField(max_length=20, choices=[('Opener', 'Opener'), ('Mid Term', 'Mid Term'), ('End Term', 'End Term')])
    marks = models.FloatField(default=0)
    remark = models.TextField(blank=True, null=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'learning_area', 'term', 'year', 'exam_type')
        db_table = 'learning_area_marks'

    def __str__(self):
        return f"{self.student.registration_no} - {self.learning_area.name} ({self.exam_type})"
class Fee(models.Model):
    registration_no = models.ForeignKey(StudentInfo,on_delete = models.CASCADE)
    school = models.ForeignKey(MasterSchool, on_delete=models.CASCADE, related_name="fees")
    mode_of_payment = models.CharField(max_length=10, blank=True, null=True)
    transaction_code = models.CharField(max_length=30, blank=True, null=True)
    
    amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    checkout_id = models.CharField(max_length=100, blank=True)
    date_of_payment = models.DateField(blank=True, null=True)
    time = models.TimeField(blank=True, null=True, auto_now_add=True)
    term = models.CharField(max_length=6, blank=True, null=True)    
    year = models.IntegerField(blank=True, null=True, default=timezone.now().year)

    status_choices = ['Pending', 'Confirmed', 'Rejected']
    status = models.CharField(max_length=10, choices=[(status, status) for status in status_choices], default='Pending')
    

    class Meta:
        # Let Django manage the table name 'students_fee'
        db_table = 'fee'
class StudentAttendance(models.Model):
    id = models.AutoField(primary_key=True)
    school = models.ForeignKey(MasterSchool, on_delete=models.CASCADE, related_name="attendance")
    registration_no = models.ForeignKey(StudentInfo,on_delete=models.CASCADE)
    
    date_of_attendance = models.DateField(blank=True, null=True)
    term = models.CharField(max_length=20, blank=True, null=True)
    time = models.TimeField(blank=True, null=True, default=timezone.now)
    year = models.IntegerField(blank=True, null=True, default=timezone.now().year)
    status = models.CharField(max_length=10, blank=True, null=True)

    

    class Meta:
        db_table = 'student_attendance'
class Strand(models.Model):
    school = models.ForeignKey("MasterSchool",on_delete = models.CASCADE)
    grade = models.CharField(max_length = 10,default = '')
    stream = models.CharField(max_length = 10,default = '')
    subject = models.CharField(max_length = 100,default = '')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'strand'
    def __str__(self):
        return f"{self.subject} - {self.name}"

class SubStrand(models.Model):
    strand = models.ForeignKey(Strand, on_delete=models.CASCADE, related_name='sub_strands')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sub_strand'
    def __str__(self):
        return f"{self.strand.name} - {self.name}"


class SubStrandMark(models.Model):
    student = models.ForeignKey('StudentInfo', on_delete=models.CASCADE)
    sub_strand = models.ForeignKey(SubStrand, on_delete=models.CASCADE)
    term = models.CharField(max_length=20)
    year = models.IntegerField()
    raw_score = models.FloatField(default=0)
    score = models.FloatField()
    remark = models.CharField(max_length = 300,default="Good")
    level = models.PositiveSmallIntegerField(choices=[(1,'Level 1'),(2,'Level 2'),(3,'Level 3'),(4,'Level 4')],default=1) 
    assessement_type = models.CharField(max_length=100,default='SBA-Written') 
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    date_recorded = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'sub_strand', 'term', 'year')
        db_table = 'sub_strand_marks'

    def __str__(self):
        return f"{self.student.registration_no} - {self.sub_strand.name} ({self.term})"

class LearnerCompetency(models.Model):
    school = models.ForeignKey(MasterSchool, on_delete=models.CASCADE, related_name='cbc_competencies')
    student = models.ForeignKey(StudentInfo, on_delete=models.CASCADE, related_name='cbc_competencies')
    grade = models.CharField(max_length=20,default='')
    stream = models.CharField(max_length=20,default='')
    subject = models.CharField(max_length=100,default='')
    term = models.CharField(max_length=20)
    year = models.IntegerField(default=timezone.now().year)

    competency = models.CharField(max_length=100)  # e.g., Communication, Critical thinking...
    level = models.PositiveSmallIntegerField(choices=[(1,'Level 1'),(2,'Level 2'),(3,'Level 3'),(4,'Level 4')])
    comment = models.CharField(max_length=300, blank=True, null=True)

    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student','term','year','competency')
        ordering = ['student_id','competency']
        db_table = 'learner_competency'

    def __str__(self):
        return f"{self.student.registration_no} - {self.competency} L{self.level}"


class GradeStreamConfig(models.Model):
    school = models.ForeignKey(MasterSchool, on_delete=models.CASCADE, related_name="streams")
    grade = models.CharField(max_length=20)
    stream = models.CharField(max_length=20)

    

    class Meta:
        unique_together = ('school', 'grade', 'stream')
        verbose_name_plural = "Grade Streams"
        db_table = 'grade_stream_config'

class GradeFeeConfig(models.Model):
    school = models.ForeignKey(MasterSchool, on_delete=models.CASCADE, related_name="grades")
    grade = models.CharField(max_length=50)
    expected_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    term = models.CharField(max_length=10, default='Term 1')

    

    class Meta:
        unique_together = ('school', 'grade')
        db_table = 'grade_fee_config'

    def __str__(self):
        return self.name

class LeaveManagement(models.Model):
    student = models.ForeignKey(StudentInfo,on_delete = models.CASCADE)
    school = models.ForeignKey(MasterSchool, on_delete=models.CASCADE, related_name="leaves")
    target = models.CharField(max_length=10, blank=True, null=True)
    reason = models.CharField(max_length=50, blank=True, null=True)
    other_reason = models.CharField(max_length=50, blank=True, null=True)
    term = models.CharField(max_length=10)
    status = models.CharField(max_length=10, blank=True, null=True)
    phone = models.BigIntegerField()
    date_of_leave = models.DateField(blank=True, null=True)
    return_date = models.DateField(blank=True, null=True)
    year = models.IntegerField(blank=True, null=True, default=timezone.now().year)
    time = models.TimeField(blank=True, null=True, default=timezone.now)

    
    
    class Meta:
        
        db_table = 'student_leave'

class StudentNote(models.Model):
    student = models.ForeignKey(StudentInfo, on_delete=models.CASCADE)
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE)
    content = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'resource')
        db_table = 'student_note'
class LearningLog(models.Model):

    student = models.ForeignKey(StudentInfo, on_delete=models.CASCADE)
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE)
    progress = models.IntegerField(default=0)
    watched_at = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False) # For tracking if they finished it

    class Meta:
        unique_together = ('student', 'resource') # Prevents double counting the same resource
        db_table = 'learning_log'







class ContactMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    subject = models.CharField(max_length=200, default='')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Contact Message"
        db_table = 'contact_message'

    def __str__(self):
        return f"{self.name} - {self.subject}"

# announcement model
class Announcement(models.Model):
    school = models.ForeignKey(MasterSchool, on_delete=models.CASCADE, related_name="announcements")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="announcements_made")
    title = models.CharField(max_length=200)
    content = models.TextField()
    target_audience = models.CharField(max_length=100, default='All') # e.g. "Students,Teachers" or "All"
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Announcement"
        ordering = ['-created_at']
        db_table = 'announcements'

    def __str__(self):
        return f"{self.title} ({self.created_at.strftime('%Y-%m-%d')})"


from django.db import models

class Reviews(models.Model):
    USER_TYPES = (
        ('student', 'Student'),
        ('teacher', 'Teacher'),
        ('parent', 'Parent'),
        ('Admin', 'School Admin'),
    )

    full_name = models.CharField(max_length=100)
    user_type = models.CharField(max_length=20, choices=USER_TYPES)
    school = models.ForeignKey(MasterSchool, on_delete=models.CASCADE, related_name="reviews")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_written", null=True, blank=True)
    location = models.CharField(max_length=100, help_text="e.g. Nairobi, Kenya")
    content = models.TextField(verbose_name="Review Message")
    rating = models.IntegerField(default=5)  # Scale of 1-5
    is_approved = models.BooleanField(default=False)  # Admin must approve
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reviews'
    def __str__(self):
        return f"{self.full_name} - {self.school}"
    
