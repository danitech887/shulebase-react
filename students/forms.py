from django import forms
from .models import *

# -------------------------
# Helpers
# -------------------------
def get_student_registration_choices():
    return [(f"REG{str(i).zfill(4)}", f"REG{str(i).zfill(4)}") for i in range(1, 10001)]

def get_teacher_registration_choices():
    return [(f"TCH{str(i).zfill(3)}", f"TCH{str(i).zfill(3)}") for i in range(1, 201)]


# -------------------------
# Grade & Stream Form
# -------------------------
class GradeStreamForm(forms.ModelForm):
    class Meta:
        model = GradeStream
        fields = ['grade', 'stream']
        widgets = {
            'grade': forms.TextInput(attrs={'class': 'form-control'}),
            'stream': forms.TextInput(attrs={'class': 'form-control'}),
        }


# -------------------------
# Student Registration
# -------------------------
class RegisterForm(forms.ModelForm):
    GENDER_CHOICES = [('Male', 'Male'), ('Female', 'Female')]
    # registration_no = forms.ChoiceField(choices=get_student_registration_choices(),widget=forms.Select(attrs={'class': 'form-control'}))
    gender = forms.ChoiceField(choices=GENDER_CHOICES, widget=forms.Select(attrs={'class': 'form-control'}))
    date_of_birth = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    date_of_registration = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))

    grade = forms.ChoiceField(choices=[('', 'Select Grade')], widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_grade'}))
    stream = forms.ChoiceField(choices=[('', 'Select Stream')], widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_stream'}))

    class Meta:
        model = StudentInfo 
        fields = [
            'registration_no', 'first_name', 'second_name', 'surname',
            'gender', 'date_of_birth', 'grade', 'stream',
            'date_of_registration','parent_name', 'phone', 'address'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'second_name': forms.TextInput(attrs={'class': 'form-control'}),
            'surname': forms.TextInput(attrs={'class': 'form-control'}),
            'parent_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        grades = list(GradeStream.objects.values_list('grade', flat=True).distinct().order_by('grade'))
        self.fields['grade'].choices = [('', 'Select Grade')] + [(g, g) for g in grades]

        selected_grade = (
            self.data.get(self.add_prefix('grade'))
            or self.initial.get('grade')
            or getattr(self.instance, 'grade', None)
        )

        streams = []
        if selected_grade:
            streams = list(
                GradeStream.objects.filter(grade=selected_grade)
                .values_list('stream', flat=True).distinct().order_by('stream')
            )
        self.fields['stream'].choices = [('', 'Select Stream')] + [(s, s) for s in streams]

    def clean(self):
        cleaned = super().clean()
        grade, stream = cleaned.get('grade'), cleaned.get('stream')
        if grade and stream:
            if not GradeStream.objects.filter(grade=grade, stream=stream).exists():
                self.add_error('stream', 'Selected stream is not available for the chosen grade.')
        return cleaned


# -------------------------
# Fees
# -------------------------
class FeeForm(forms.ModelForm):
    class Meta:
        model = Fee
        fields = ['registration_no', 'term', 'mode_of_payment', 'amount', 'transaction_code', 'date_of_payment']
        widgets = {
            'term': forms.Select(attrs={'class': 'form-control'}, choices=[('Term 1', 'Term 1'), ('Term 2', 'Term 2'), ('Term 3', 'Term 3')]),
            'mode_of_payment': forms.Select(attrs={'class': 'form-control'}, choices=[('Mpesa', 'Mpesa'), ('Cash', 'Cash')]),
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'transaction_code': forms.TextInput(attrs={'class': 'form-control'}),
            'date_of_payment': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }


class GradeFeeForm(forms.ModelForm):
    class Meta:
        model = Grade
        fields = ['expected_fee']


# -------------------------
# Leave
# -------------------------
class LeaveForm(forms.ModelForm):
    class Meta:
        model = LeaveManagement
        exclude = ['school', 'phone']
        widgets = {
            'term': forms.Select(attrs={'class': 'form-control'}, choices=[('Term 1', 'Term 1'), ('Term 2', 'Term 2'), ('Term 3', 'Term 3')]),
            'date_of_leave': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'reason': forms.Select(attrs={'class': 'form-control'}, choices=[('School Fees', 'School Fees'), ('Other Reason', 'Other Reason')]),
            'return_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'other_reason': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }


# -------------------------
# Teachers
# -------------------------
class RegisterTeacherForm(forms.ModelForm):


    registration_no = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'})
    )

    class Meta:
        GENDER_CHOICES = [('Male', 'Male'), ('Female', 'Female')] 

        model = TeacherInfo
        fields = [
            'registration_no', 'first_name', 'second_name', 'surname',
            'gender', 'phone', 'email', 'address', 'date_of_registration'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'second_name': forms.TextInput(attrs={'class': 'form-control'}),
            'surname': forms.TextInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(choices=GENDER_CHOICES, attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'date_of_registration': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        }


class TeacherAttendanceForm(forms.ModelForm):
    status = forms.ChoiceField(choices=[('Present', 'Present'), ('Absent', 'Absent')], widget=forms.RadioSelect)

    class Meta:
        model = TeacherAttendance
        fields = ['registration_no', 'status', 'date_of_attendance', 'time_in']
        widgets = {
            'date_of_attendance': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'time_in': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['registration_no'].queryset = TeacherInfo.objects.all()
        self.fields['registration_no'].widget.attrs.update({'class': 'form-select'})


# -------------------------
# Teaching Progress
# -------------------------
class TeachingProgressForm(forms.ModelForm):
    STATUS_CHOICES = [('Completed', 'Completed'), ('Ongoing', 'Ongoing')]

    status = forms.ChoiceField(choices=STATUS_CHOICES, widget=forms.Select(attrs={'class': 'form-control'}))
    

    class Meta:
        model = TeachingProgress
        fields = ['grade', 'stream', 'subject', 'no_of_topics', 'topic', 'sub_topic', 'date_of_teaching', 'date_finished', 'status']
        widgets = {
            'grade': forms.Select(attrs={'class': 'form-control'}),
            'stream': forms.Select(attrs={'class': 'form-control'}),
            'subject': forms.Select(attrs={'class': 'form-control'}),
            
            'no_of_topics': forms.NumberInput(attrs={'class': 'form-control'}),
            'topic': forms.TextInput(attrs={'class': 'form-control'}),
            'sub_topic': forms.TextInput(attrs={'class': 'form-control'}),
            'date_of_teaching': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'date_finished': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }


# -------------------------
# School Registration
# -------------------------
class SchoolRegistrationForm(forms.ModelForm):
    logo_path = forms.ImageField(required=False, widget=forms.ClearableFileInput(attrs={'class': 'form-control'}))

    class Meta:
        model = MasterSchool
        fields = ['school_name', 'po_box', 'address', 'contact', 'email_address', 'motto', 'vision', 'logo_path']
        widgets = {
            'school_name': forms.TextInput(attrs={'class': 'form-control'}),
            'po_box': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'contact': forms.TextInput(attrs={'class': 'form-control'}),
            'email_address': forms.EmailInput(attrs={'class': 'form-control'}),
            'motto': forms.TextInput(attrs={'class': 'form-control'}),
            'vision': forms.TextInput(attrs={'class': 'form-control'}),
        }


# -------------------------
# Contact
# -------------------------
class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'subject', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Your Email'}),
            'subject': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Subject'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Your Message'}),
        }


from django import forms
from .models import Strand

class StrandForm(forms.ModelForm):
    class Meta:
        model = Strand
        fields = ["grade","stream","name","subject"]

        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter strand name"}),
            "grade": forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter strand name"}),
            "stream": forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter strand name"}),
            "subject": forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter strand name"}),
        }
 

class SubstrandReportForm(forms.Form):
    # Assuming 'Substrand' is the model where you store your substrands
    substrand = forms.ModelChoiceField(
        queryset=SubStrand.objects.all().order_by('name'),
        label="Select Substrand",
        empty_label="--- Select a Substrand ---",
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class ResourceForm(forms.ModelForm):
    class Meta:
        model = Resource
        fields = ['title', 'subject', 'grade','stream','term', 'resource_type', 'url_or_file', 'thumbnail']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'subject': forms.TextInput(attrs={'class': 'form-control'}),
            'grade': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Grade 1'}),
            'term': forms.Select(attrs={'class': 'form-control'}), 
            'resource_type': forms.Select(attrs={'class': 'form-select'}),
            'url_or_file': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'YouTube ID or External URL'}),
        }