import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from core.models import Strand, SubStrand

subject = 'Creative Arts'
grade = 'Grade 3'
stream = 'A'

strands = Strand.objects.filter(grade=grade, stream=stream, subject__iexact=subject)
print(f"Found {strands.count()} strands for {subject}")
for s in strands:
    subs = s.sub_strands.all()
    print(f"Strand: {s.name}, Substrands: {subs.count()}")
