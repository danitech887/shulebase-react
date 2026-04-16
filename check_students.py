import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from core.models import StudentInfo

grade = 'Grade 3'
stream = 'A'

students = StudentInfo.objects.filter(grade=grade, stream=stream)
print(f"Found {students.count()} students for {grade} {stream}")
for s in students:
    print(f"Student: {s.first_name} {s.surname}, Reg: {s.registration_no}")
