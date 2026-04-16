from rest_framework import serializers

from .models import*


class StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentInfo
        fields = '__all__'

class LeaveManagementSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveManagement
        fields = '__all__'

class TeacherSerializer(serializers.ModelSerializer):
    date_of_registration = serializers.DateField(input_formats=['%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%d'], required=False, allow_null=True)
    class Meta:
        model = TeacherInfo
        fields = '__all__'

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = Users
        fields = '__all__'
        extra_kwargs = {
            'password': {'write_only': True}
        }
    def create(self,validated_data):
        return Users.objects.create_user(**validated_data) 
class SchoolRegistrationSerializer(serializers.ModelSerializer):
    username = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    class Meta:
        model = MasterSchool
        fields = '__all__' # Adjust fields as needed

    def validate_email_address(self, value):
        # Exclude current instance when updating to allow using the same email
        qs = MasterSchool.objects.filter(email_address=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        
        if qs.exists():
            raise serializers.ValidationError("Email is already registered to another school.")
        return value

    def validate_username(self, value):
        if Users.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username is already taken.")
        return value

    def create(self, validated_data):
        username = validated_data.pop('username')
        password = validated_data.pop('password')
        
        # Use an atomic transaction to ensure both or neither are created
        with transaction.atomic():
            school = MasterSchool.objects.create(**validated_data)
            Users.objects.create_user(
                school=school,
                username=username,
                email=school.email_address,
                password=password,
                role='Admin',
                school_name=school.school_name,
            )
        return school

class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeachersRole
        fields = '__all__'

class FeeRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fee
        fields = '__all__'


class GradeStreamSerializer(serializers.ModelSerializer):
    class Meta:
        model = GradeStreamConfig
        fields = '__all__'

class TeachersRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeachersRole
        fields = "__all__"


class StudentInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentInfo
        fields = ["registration_no", "first_name", "surname", "grade", "stream"]


class StudentAttendanceSerializer(serializers.ModelSerializer):
    pupil = StudentInfoSerializer(source="registration_no", read_only=True)

    class Meta:
        model = StudentAttendance
        fields = ["id", "registration_no", "pupil", "date_of_attendance", "status", "term", "year", "time"]
        read_only_fields = ["year", "time"]


class AttendanceWriteSerializer(serializers.Serializer):
    """Used for bulk-creating attendance records."""
    grade = serializers.CharField()
    stream = serializers.CharField()
    term_select = serializers.CharField()
    # statuses: { "REG_NO": "Present"|"Absent" }
    statuses = serializers.DictField(child=serializers.ChoiceField(choices=["Present", "Absent"]))

class SubStrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubStrand
        fields = ["id", "strand", "name", "description", "created_by", "created_at"]
        read_only_fields = ["created_by", "created_at"]


class StrandSerializer(serializers.ModelSerializer):
    # include nested sub-strands so the frontend can render them without extra requests
    sub_strands = SubStrandSerializer(many=True, read_only=True)

    class Meta:
        model = Strand
        fields = ["id", "name", "subject", "grade", "stream", "school", "created_by", "sub_strands"]
        read_only_fields = ["school", "created_by"]




class SubStrandMarkSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubStrandMark
        fields = ["id", "student", "sub_strand", "term", "year", "score", "remark", "recorded_by"]
        read_only_fields = ["recorded_by", "year"]


class TeachingProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeachingProgress
        fields = "__all__"
        read_only_fields = ["registration_no", "school"]


class ResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resource
        fields = "__all__"
        read_only_fields = ["uploaded_by", "school"]

class LearningLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = LearningLog
        fields = "__all__"
        read_only_fields = ["recorded_by", "school", "date_recorded"]

class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = "__all__"
        read_only_fields = ["created_by", "school", "created_at"]


class LearnerCompetencySerializer(serializers.ModelSerializer):
    class Meta:
        model = LearnerCompetency
        fields = "__all__"
        read_only_fields = ["recorded_by", "school", "date_recorded"]


class LearningAreaMarkSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = LearningAreaMark
        fields = "__all__"
        read_only_fields = ["recorded_by", "school", "recorded_at", "year"]

    def get_student_name(self, obj):
        return f"{obj.student.first_name} {obj.student.surname}"


class TeacherLeaveSerializer(serializers.ModelSerializer):
    teacher_name = serializers.SerializerMethodField(read_only=True)
    reg_no       = serializers.SerializerMethodField(read_only=True)
    grade        = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = TeacherLeave
        fields = [
            'id', 'school', 'teacher',
            'teacher_name', 'reg_no', 'grade',
            'leave_type', 'reason',
            'start_date', 'end_date', 'duration',
            'status', 'applied_on',
            'admin_note', 'reviewed_by', 'reviewed_on',
        ]
        read_only_fields = ['duration', 'applied_on', 'reviewed_by', 'reviewed_on']

    def get_teacher_name(self, obj):
        return f"{obj.teacher.first_name} {obj.teacher.surname}"

    def get_reg_no(self, obj):
        return obj.teacher.registration_no

    def get_grade(self, obj):
        # Return the grade the teacher is assigned to (if any)
        role = obj.teacher.teachersrole_set.filter(school_id=obj.school_id).first()
        return role.grade if role else '—'


class ReviewsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reviews
        fields = "__all__"
        read_only_fields = ["created_by", "school", "is_approved", "created_at", "full_name", "user_type"]


class PublicSchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = MasterSchool
        fields = ["id", "school_name", "logo_path"]