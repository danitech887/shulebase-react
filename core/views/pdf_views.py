"""
views.py  –  PDF report views (restyled)
All visual work delegated to pdf_styles.py.
"""

import csv
import io
import zipfile
from collections import defaultdict
from decimal import Decimal
from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import status

from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.db.models import Sum, Q, Avg, Count, F
from django.utils.timezone import now
from fpdf import FPDF

from core.models import (

    MasterSchool, StudentInfo, SubStrandMark, 
     Strand, LearnerCompetency,
    Fee, GradeFeeConfig, LeaveManagement,
    StudentAttendance, LearningArea, LearningAreaMark,
)

# ── Design-system import ──────────────────────────────────────────────────────
from .pdf_styles import (
     PdfReciept, PdfReportForm,
    pdf_header, pdf_footer,
    draw_section_title, draw_styled_table_header, draw_styled_row,
    CBC_LEVEL_MAP, get_cbc_level_and_remark, core_competencies,
    NAVY, GOLD, SKY, WHITE, MID, GREEN, CRIMSON, BLACK,GREY,
    _set_fill, _set_text, _set_draw,
)

# Keep FPDF available for any local one-off usage
from fpdf import FPDF


# ─────────────────────────────────────────────────────────────────────────────
# RESULT PAPERS (zipped by grade group)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def generate_result_papers(request):
    school_id = request.user.school_id
    messages.get_messages(request).used = True

    grade_filter = request.GET.get('grade', '')
    stream_filter = request.GET.get('stream', '')
    term_filter = request.GET.get('term', '')
    assessement_type_filter = request.GET.get('assessement_type', '') or request.GET.get('exam_type', '')

    grade_configs = {
        "lower": {
            "grades": ["Grade 1", "Grade 2", "Grade 3"],
            "columns": [
                ('Reg No',15),('Name',40),('Grade',12),('Stream',12),
                ('Maths',13),('Eng',13),('Kisw',13),('Env Act',13),
                ('Inte/Cre',14),('Total',13),('Mean',13),('Pos',12),('O/Pos',12),
            ],
            "fields": ["mathematics","english","kiswahili","environmental_activities","integrated_creative"],
        },
        "upper": {
            "grades": ["Grade 4","Grade 5","Grade 6"],
            "columns": [
                ('Reg No',15),('Name',37),('Grade',12),('Stream',12),
                ('Maths',12),('Eng',12),('Kisw',12),('Sci&Tech',13),
                ('SST/CRE',13),('Agri&Nutr',13),('CreArts',12),
                ('Total',12),('Mean',12),('Pos',11),('O/Pos',11),
            ],
            "fields": ["mathematics","english","kiswahili","science_technology","sst_cre","agri_nutrition","creative_arts"],
        },
        "junior": {
            "grades": ["Grade 7","Grade 8","Grade 9"],
            "columns": [
                ('Reg No',14),('Name',35),('Grade',10),('Stream',10),
                ('Maths',11),('Eng',11),('Kisw',11),('SST/CRE',12),
                ('Agri&Nutr',12),('CreArts',11),('Pre/Bs',12),
                ('InteSci',11),('Total',11),('Mean',11),('Pos',10),('O/Pos',10),
            ],
            "fields": ["mathematics","english","kiswahili","sst_cre","agri_nutrition","creative_arts","pretech_bs_computer","integrated_science"],
        },
    }

    # ── Sub-tasks ─────────────────────────────────────────────────────────────
    def get_students_and_marks(g, term, exam_type):
        marks_qs = Marks.objects.select_related('registration_no').filter(
            school_id=school_id, registration_no__grade=g,
            term=term, type_of_exam=exam_type
        ).exclude(total_marks__isnull=True).exclude(total_marks=0)
        students = StudentInfo.objects.filter(
            school_id=school_id,
            registration_no__in=marks_qs.values_list('registration_no__registration_no', flat=True),
        )
        return marks_qs, {s.registration_no: s for s in students}

    def write_pdf_to_zip(pdf, filename, zf):
        zf.writestr(filename, pdf.output(dest='S').encode('latin1'))

    def generate_pdf_for_group(group_name, config, zf):
        for g in config["grades"]:
            if grade_filter and grade_filter != g:
                continue
            marks_qs, student_map = get_students_and_marks(g, term_filter, assessement_type_filter)
            if not marks_qs.exists():
                continue

            pdf = FPDF()
            pdf.add_page()
            pdf_header(request, pdf, 30)

            # ── Page subtitle ──
            _set_fill(pdf, SKY)
            pdf.rect(pdf.l_margin, pdf.get_y(), pdf.w - pdf.l_margin - pdf.r_margin, 8, style='F')
            _set_text(pdf, NAVY)
            pdf.set_font('Arial', 'B', 10)
            pdf.cell(0, 8, f"  {g}   |   {assessement_type_filter}   |   {term_filter}", ln=True)
            pdf.ln(2)

            # ── Column headers ──
            cols = config["columns"]
            widths = [w for _, w in cols]
            draw_styled_table_header(pdf, cols)

            # ── Rows ──
            for row_idx, mark in enumerate(marks_qs):
                student = student_map.get(mark.registration_no.registration_no)
                if not student:
                    continue
                name = f"{student.first_name} {student.second_name or ''} {student.surname or ''}".strip()
                row = [student.registration_no, name, student.grade, student.stream]
                row += [getattr(mark, f, 0) or 0 for f in config["fields"]]
                row += [mark.total_marks or 0, mark.mean_marks or 0,
                        getattr(mark, 'position', '-'), getattr(mark, 'overall_position', '-')]
                aligns = ['L','L'] + ['C'] * (len(row) - 2)
                draw_styled_row(pdf, row, widths, row_idx, aligns)

            write_pdf_to_zip(pdf, f"{g}_{term_filter}_{assessement_type_filter}_results.pdf", zf)

    # ── Build ZIP ─────────────────────────────────────────────────────────────
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        for group, config in grade_configs.items():
            generate_pdf_for_group(group, config, zf)

    zip_buf.seek(0)
    resp = HttpResponse(zip_buf, content_type='application/zip')
    resp['Content-Disposition'] = 'attachment; filename="result_papers.zip"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# ACADEMIC REPORT
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def generate_academic_report(request):
    school_id = request.user.school_id
    messages.get_messages(request).used = True

    report_type = request.GET.get('report_type', 'Overall Academic Performance')
    grade = request.GET.get('grade', '')
    fmt = request.GET.get('format', 'pdf').lower()

    if fmt != 'pdf':
        return HttpResponse('Only PDF format is supported', status=400)

    pdf = FPDF()
    pdf.add_page()
    pdf_header(request, pdf, 30)

    draw_section_title(pdf, report_type)

    _set_text(pdf, NAVY)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 8, f"Grade: {grade or 'All Grades'}", ln=True)
    pdf.ln(3)

    if grade:
        students_qs = StudentInfo.objects.filter(school_id=school_id, grade=grade).order_by('registration_no')[:200]
        if not students_qs:
            _set_text(pdf, MID)
            pdf.set_font('Arial', 'I', 10)
            pdf.cell(0, 6, 'No students found for selected grade.', ln=True)
        else:
            cols = [('Reg No', 30), ('Name', 90), ('Stream', 40)]
            draw_styled_table_header(pdf, cols)
            for i, s in enumerate(students_qs):
                name = f"{s.first_name} {s.surname or ''}".strip()
                draw_styled_row(pdf, [s.registration_no, name, s.stream or '-'],
                                [30, 90, 40], i, ['L','L','C'])
    else:
        draw_section_title(pdf, "Students Per Grade")
        grades = StudentInfo.objects.filter(school_id=school_id).values('grade').distinct()
        cols = [('Grade', 80), ('Count', 40)]
        draw_styled_table_header(pdf, cols)
        for i, g in enumerate(grades):
            gname = g.get('grade')
            cnt = StudentInfo.objects.filter(school_id=school_id, grade=gname).count()
            draw_styled_row(pdf, [gname, cnt], [80, 40], i, ['L','C'])

    pdf_footer(pdf)
    safe_grade = (grade or 'all').replace(' ', '_')
    resp = HttpResponse(pdf.output(dest='S').encode('latin1'), content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="academic_report_{safe_grade}.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# ATTENDANCE REPORT
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# 2.  ATTENDANCE REPORT (Daily, Weekly, Termly)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def print_attendance_report(request):
    school_id = request.user.school_id
    grade = request.GET.get('grade', '').strip()
    stream = request.GET.get('stream', '').strip()
    report_type = request.GET.get('report_type', 'daily').lower()
    date_str = request.GET.get('date', str(datetime.now().date()))
    term = request.GET.get('term', 'Term 1')
    year = request.GET.get('year', str(datetime.now().year))
    fmt = request.GET.get('format', 'pdf').lower()

    students = StudentInfo.objects.filter(school_id=school_id, grade=grade, stream=stream).order_by('registration_no')
    print(f"DEBUG ATTENDANCE: grade='{grade}', stream='{stream}', students_found={students.count()}")
    if not students.exists():
        return HttpResponse(f"REPORT_ERROR: No students found for {grade} {stream} in school {school_id}.", status=404)

    if report_type == 'daily':
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        records = StudentAttendance.objects.filter(school_id=school_id, date_of_attendance=target_date, registration_no__in=students)
        status_map = {r.registration_no.registration_no: r.status for r in records}
        
        if fmt == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="attendance_daily_{grade}_{date_str}.csv"'
            writer = csv.writer(response)
            writer.writerow(['Reg No', 'Name', 'Status'])
            for s in students:
                writer.writerow([s.registration_no, f"{s.first_name} {s.surname}", status_map.get(s.registration_no, 'Absent')])
            return response

        pdf = FPDF()
        pdf.add_page()
        pdf_header(request, pdf, 30)
        draw_section_title(pdf, f"Daily Attendance: {grade} {stream}")
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 8, f"Date: {date_str}  |  Term: {term}", ln=True)
        pdf.ln(4)
        
        cols = [('Reg No', 40), ('Name', 100), ('Status', 40)]
        draw_styled_table_header(pdf, cols)
        for i, s in enumerate(students):
            st = status_map.get(s.registration_no, 'Absent')
            clr = GREEN if st == 'Present' else CRIMSON
            draw_styled_row(pdf, [s.registration_no, f"{s.first_name} {s.surname}", st], [40, 100, 40], i, ['L', 'L', 'C'])
        
        return HttpResponse(pdf.output(dest='S').encode('latin1'), content_type='application/pdf')

    elif report_type == 'weekly':
        # Matrix of 5 days (Mon-Fri) for the week containing target_date
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        start = target_date - timedelta(days=target_date.weekday())
        days = [start + timedelta(days=i) for i in range(5)] # Mon-Fri
        
        records = StudentAttendance.objects.filter(school_id=school_id, date_of_attendance__range=(days[0], days[-1]), registration_no__in=students)
        grid = defaultdict(dict)
        for r in records:
            grid[r.registration_no.registration_no][r.date_of_attendance] = r.status

        if fmt == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="attendance_weekly_{grade}_{date_str}.csv"'
            writer = csv.writer(response)
            header = ['Reg No', 'Name'] + [d.strftime('%a %d') for d in days]
            writer.writerow(header)
            for s in students:
                row = [s.registration_no, f"{s.first_name} {s.surname}"]
                for d in days: row.append(grid[s.registration_no].get(d, 'A'))
                writer.writerow(row)
            return response

        pdf = FPDF(orientation='L')
        pdf.add_page()
        pdf_header(request, pdf, 30)
        draw_section_title(pdf, f"Weekly Attendance Matrix: {grade} {stream}")
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 8, f"Week Starting: {days[0]}  |  Term: {term}", ln=True)
        pdf.ln(4)

        col_w = (pdf.w - 100) / 5
        cols = [('Reg Mo', 30), ('Student Name', 70)] + [(d.strftime('%a %d'), col_w) for d in days]
        draw_styled_table_header(pdf, cols)
        for i, s in enumerate(students):
            row = [s.registration_no, f"{s.first_name} {s.surname}"[:25]]
            for d in days:
                st = grid[s.registration_no].get(d, 'A')
                row.append('P' if st == 'Present' else 'A')
            draw_styled_row(pdf, row, [30, 70] + [col_w]*5, i, ['L','L'] + ['C']*5)
        
        return HttpResponse(pdf.output(dest='S').encode('latin1'), content_type='application/pdf')

    elif report_type == 'termly':
        records = StudentAttendance.objects.filter(school_id=school_id, term=term, year=year, registration_no__in=students)
        summary = {}
        for s in students: summary[s.registration_no] = {'P':0, 'A':0}
        for r in records:
            if r.status == 'Present': summary[r.registration_no.registration_no]['P'] += 1
            else: summary[r.registration_no.registration_no]['A'] += 1
            
        if fmt == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="attendance_termly_{grade}_{term}.csv"'
            writer = csv.writer(response)
            writer.writerow(['Reg No', 'Name', 'Present', 'Absent', '%'])
            for s in students:
                counts = summary[s.registration_no]
                total = counts['P'] + counts['A']
                pct = round((counts['P']/total*100), 1) if total > 0 else 0
                writer.writerow([s.registration_no, f"{s.first_name} {s.surname}", counts['P'], counts['A'], f"{pct}%"])
            return response

        pdf = FPDF()
        pdf.add_page()
        pdf_header(request, pdf, 30)
        draw_section_title(pdf, f"Termly Attendance Summary: {grade} {stream}")
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(0, 8, f"Term: {term}  |  Year: {year}", ln=True)
        pdf.ln(4)

        cols = [('Reg No', 30), ('Name', 80), ('Present', 25), ('Absent', 25), ('%', 20)]
        draw_styled_table_header(pdf, cols)
        for i, s in enumerate(students):
            c = summary[s.registration_no]
            t = c['P'] + c['A']
            p = round((c['P']/t*100), 1) if t > 0 else 0
            draw_styled_row(pdf, [s.registration_no, f"{s.first_name} {s.surname}", c['P'], c['A'], f"{p}%"], [30, 80, 25, 25, 20], i, ['L','L','C','C','C'])

        return HttpResponse(pdf.output(dest='S').encode('latin1'), content_type='application/pdf')

    return HttpResponse("Invalid report type", status=400)


# ─────────────────────────────────────────────────────────────────────────────
# 3.  AGGREGATED SUBJECT PERFORMANCE REPORT
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def print_subject_aggregated_report(request):
    school_id = request.user.school_id
    grade = request.GET.get('grade', '').strip()
    stream = request.GET.get('stream', '').strip()
    subject = request.GET.get('subject', '').strip()
    term = request.GET.get('term', 'Term 1')
    year = request.GET.get('year', str(datetime.now().year))
    fmt = request.GET.get('format', 'pdf').lower()

    if not all([grade, subject]):
        return HttpResponse("Missing grade or subject", status=400)

    students = StudentInfo.objects.filter(school_id=school_id, grade=grade, stream=stream).order_by('registration_no')
    strands = Strand.objects.filter(school_id=school_id, grade=grade, stream=stream, subject__iexact=subject).prefetch_related('sub_strands')
    sub_strands = []
    for st in strands:
        sub_strands.extend(list(st.sub_strands.all()))
    
    print(f"DEBUG SUBJECT: grade='{grade}', stream='{stream}', subject='{subject}', students={students.count()}, topics={len(sub_strands)}")
    
    if not students.exists():
         return HttpResponse(f"REPORT_ERROR: No students found for {grade} {stream} in school {school_id}.", status=404)

    if not sub_strands:
        return HttpResponse(f"REPORT_ERROR: No topics found for {subject} in {grade}.", status=404)

    marks = SubStrandMark.objects.filter(sub_strand__in=sub_strands, term=term, year=year)
    mark_grid = defaultdict(dict)
    for m in marks:
        mark_grid[m.student.registration_no][m.sub_strand_id] = {'score': m.score, 'level': m.level}

    if fmt == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="subject_performance_{subject}_{grade}.csv"'
        writer = csv.writer(response)
        headers = ['Reg No', 'Name'] + [ss.name for ss in sub_strands] + ['Avg Score', 'Avg Level', 'Rating']
        writer.writerow(headers)
        for s in students:
            row = [s.registration_no, f"{s.first_name} {s.surname}"]
            scores = []
            levels = []
            for ss in sub_strands:
                val = mark_grid[s.registration_no].get(ss.id)
                if val:
                    row.append(f"{val['score']}% (L{val['level']})")
                    scores.append(val['score'])
                    levels.append(val['level'])
                else:
                    row.append('-')
            avg_s = round(sum(scores)/len(scores), 1) if scores else 0
            avg_l = round(sum(levels)/len(levels), 1) if levels else 0
            rating = get_cbc_level_and_remark(avg_l)['level']
            row += [avg_s, avg_l, rating]
            writer.writerow(row)
        return response

    # ── PDF ──────────────────────────────────────────────────────────────────
    pdf = FPDF(orientation='L')
    pdf.add_page()
    pdf_header(request, pdf, 30)
    draw_section_title(pdf, f"Aggregated Subject Performance: {subject}")
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(0, 7, f"Grade: {grade} {stream} | Term: {term} | Year: {year}", ln=True)
    pdf.ln(3)

    # Dynamic columns
    base_widths = [15, 30] # Reg, Name
    avail = pdf.w - pdf.l_margin - pdf.r_margin - 45 - 35 # Reserve 35 for aggregates
    topic_w = avail / max(len(sub_strands), 1)
    
    cols = [('Reg', 15), ('Student Name', 30)]
    for ss in sub_strands:
        cols.append((ss.name[:12], topic_w))
    cols += [('Avg%', 12), ('Level', 11), ('Rating', 12)]
    
    draw_styled_table_header(pdf, cols)
    widths = [w for _, w in cols]

    for i, s in enumerate(students):
        row = [s.registration_no, f"{s.first_name} {s.surname}"[:20]]
        scores = []
        levels = []
        for ss in sub_strands:
            val = mark_grid[s.registration_no].get(ss.id)
            if val:
                row.append(f"L{val['level']}")
                scores.append(val['score'])
                levels.append(val['level'])
            else:
                row.append('-')
        
        avg_s = round(sum(scores)/len(scores), 1) if scores else 0
        avg_l = round(sum(levels)/len(levels), 1) if levels else 0
        rating = get_cbc_level_and_remark(avg_l)['level']
        row += [avg_s, avg_l, rating]
        
        draw_styled_row(pdf, row, widths, i, ['L','L'] + ['C']*(len(row)-2))

    pdf_footer(pdf)
    return HttpResponse(pdf.output(dest='S').encode('latin1'), content_type='application/pdf')


# ─────────────────────────────────────────────────────────────────────────────
# REPORT FORMS (per-student CBC)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def print_report_forms(request):
    school_id = request.user.school_id
    messages.get_messages(request).used = True

    term  = request.GET.get('term')
    grade = request.GET.get('grade')
    stream = request.GET.get('stream')
    registration_no = request.GET.get('registration_no')
    year = request.GET.get('year', str(datetime.now().year))

    # ── Marks aggregation ────────────────────────────────────────────────────
    mf = Q(sub_strand__strand__isnull=False, term=term, year=year)
    if grade:
        mf &= Q(sub_strand__strand__grade=grade)
    if stream:
        mf &= Q(student__stream=stream)
    if registration_no:
        mf &= Q(student__registration_no=registration_no)

    all_marks_qs = SubStrandMark.objects.filter(mf)
    student_subject_averages = all_marks_qs.values(
        'student__registration_no','sub_strand__strand__subject'
    ).annotate(
        avg_subject_level=Avg('level'),
        avg_subject_score=Avg('score'),
        total_sub_strand_marks=Count('id'),
        project_score=Avg('level', filter=Q(assessement_type='SBA-Project')),
        practical_score=Avg('level', filter=Q(assessement_type='SBA-Practical')),
        written_score=Avg('level', filter=Q(assessement_type='SBA-Written')),
    ).filter(total_sub_strand_marks__gt=0)

    subject_data_lookup = defaultdict(lambda: defaultdict(lambda: {
        'level':None,'score':None,'project':None,'practical':None,'written':None
    }))
    for d in student_subject_averages:
        rn   = d['student__registration_no']
        subj = d.get('sub_strand__strand__subject')
        if subj:
            subject_data_lookup[rn][subj]['level']     = d['avg_subject_level']
            subject_data_lookup[rn][subj]['score']     = d['avg_subject_score']
            subject_data_lookup[rn][subj]['project']   = d['project_score']
            subject_data_lookup[rn][subj]['practical'] = d['practical_score']
            subject_data_lookup[rn][subj]['written']   = d['written_score']

    reg_nos = student_subject_averages.values_list('student__registration_no', flat=True).distinct()
    students = StudentInfo.objects.filter(school_id=school_id, registration_no__in=reg_nos)
    student_map = {s.registration_no: s for s in students}

    avg_mean_level, overall_avg_score = {}, {}
    for rn in reg_nos:
        data   = subject_data_lookup[rn].values()
        levels = [d['level'] for d in data if d['level'] is not None]
        scores = [d['score'] for d in data if d['score'] is not None]
        avg_mean_level[rn]    = round(min(sum(levels)/len(levels), 4.0), 2) if levels else 0
        overall_avg_score[rn] = round(sum(scores)/len(scores), 2) if scores else 0

    # Ranking
    overall_sorted = sorted(reg_nos, key=lambda r: avg_mean_level.get(r, 0), reverse=True)
    overall_rank = {}
    current_rank, prev = 1, None
    for idx, rn in enumerate(overall_sorted, 1):
        if prev is not None and avg_mean_level[rn] != prev:
            current_rank = idx
        overall_rank[rn] = current_rank
        prev = avg_mean_level[rn]

    stream_rank = {}
    streams = set(student_map[rn].stream for rn in reg_nos if rn in student_map)
    for s in streams:
        sr = sorted([r for r in reg_nos if student_map.get(r) and student_map[r].stream == s],
                    key=lambda r: overall_avg_score.get(r, 0), reverse=True)
        rank, prev2 = 1, None
        for idx, r in enumerate(sr, 1):
            if prev2 is not None and overall_avg_score.get(r,0) != prev2:
                rank = idx
            stream_rank[r] = rank
            prev2 = overall_avg_score.get(r,0)

    subjects_in_grade = Strand.objects.filter(grade=grade, school_id=school_id)\
                                      .values_list('subject', flat=True).distinct()

    # ── PDF ──────────────────────────────────────────────────────────────────
    pdf = PdfReportForm()

    if not reg_nos:
        pdf.add_page()
        pdf_header(request, pdf, 30)
        pdf.set_font('Arial', 'I', 12)
        pdf.cell(0, 10, 'No marks found for selected criteria.', align='C')

    for rn in reg_nos:
        student = student_map.get(rn)
        if not student:
            continue

        # competency averages
        comp_summary = LearnerCompetency.objects.filter(student=student, term=term, year=year)\
                        .values('competency').annotate(avg_level=Avg('level'))
        avg_level_map = {i['competency']: i['avg_level'] for i in comp_summary}

        comp_qs = LearnerCompetency.objects.filter(student=student, term=term, year=year)\
                   .values('subject','competency','level')
        print(comp_qs.query)
        comp_map = defaultdict(dict)
        for c in comp_qs:
            comp_map[c['subject']][c['competency']] = c['level']

        pdf.add_page()
        pdf.add_background_color(245, 249, 255)
        pdf.add_watermark(student.first_name.upper())
        pdf.set_text_color(0, 0, 0)
        pdf_header(request, pdf, 30)

        # Report title
        _set_text(pdf, NAVY)
        pdf.set_font('Arial', 'BU', 13)
        pdf.cell(0, 6, 'LEARNER COMPETENCY REPORT', align='C', ln=True)
        pdf.ln(4)

        # Student banner
        full_name = f"{student.first_name} {student.second_name or ''} {student.surname or ''}".strip()
        pdf.student_info_banner(student.registration_no, full_name, student.grade, student.stream, term)
        pdf.ln(4)

        # ── Learning area table ──
        draw_section_title(pdf, "Learning Area Performance")
        la_cols = [
            ('Learning Area',40),('SBA-Proj',18),('SBA-Prac',18),('SBA-Writ',18),
            ('Avg Score',18),('Avg Level',18),('CBC Level',18),('Remark',30),
        ]
        draw_styled_table_header(pdf, la_cols)

        for row_idx, subj in enumerate(subjects_in_grade):
            data    = subject_data_lookup[rn].get(subj, {})
            avg_lv  = data.get('level')
            avg_sc  = data.get('score')
            proj    = data.get('project')
            prac    = data.get('practical')
            writ    = data.get('written')
            rep     = get_cbc_level_and_remark(avg_lv)

            row_vals = [
                subj,
                f"{round(proj,1)}" if proj is not None else "-",
                f"{round(prac,1)}" if prac is not None else "-",
                f"{round(writ,1)}" if writ is not None else "-",
                f"{round(avg_sc,1)}" if avg_sc is not None else "-",
                f"{round(avg_lv,2)}" if avg_lv is not None else "-",
                rep['level'], rep['remark'],
            ]
            aligns = ['L','C','C','C','C','C','C','C']
            draw_styled_row(pdf, row_vals, [w for _,w in la_cols], row_idx, aligns)

        pdf.ln(3)

        # ── Summary strip ──
        _set_fill(pdf, NAVY)
        pdf.rect(pdf.l_margin, pdf.get_y(), 95, 8, style='F')
        _set_text(pdf, GOLD)
        pdf.set_font('Arial', 'B', 8)
        pdf.set_x(pdf.l_margin)
        pdf.cell(47.5, 8, f"Avg Level: {avg_mean_level.get(rn, 0)}", align='C')
        pdf.cell(47.5, 8, f"Avg Score: {overall_avg_score.get(rn, 0)}%", align='C')
        pdf.ln(10)
        _set_text(pdf, BLACK)

        # ── Competency breakdown ──
        draw_section_title(pdf, "Competency Breakdown by Learning Area")
        col_w = (pdf.w - pdf.l_margin - pdf.r_margin - 35) / max(len(core_competencies), 1)
        _set_fill(pdf, NAVY)
        _set_text(pdf, GOLD)
        pdf.set_font('Arial', 'B', 5)
        pdf.cell(35, 6, 'Learning Area', border=0, fill=True, align='C')
        for comp in core_competencies:
            pdf.cell(col_w, 6, comp, border=0, fill=True, align='C')
        pdf.ln()

        for row_idx, subj in enumerate(subjects_in_grade):
            fill = SKY if row_idx % 2 == 0 else WHITE
            _set_fill(pdf, fill)
            _set_text(pdf, BLACK)
            pdf.set_font('Arial', '', 5)
            pdf.cell(35, 5, subj, border=1, fill=True, align='L')
            for comp in core_competencies:
                val = comp_map.get(subj, {}).get(comp)
                print("compes: ",comp,val)
                pdf.cell(col_w, 5, str(round(val,1)) if val else "-", border=1, fill=True, align='C')
            pdf.ln()

        pdf.ln(4)

        # ── Aggregated competency ──
        draw_section_title(pdf, "Aggregated Competency Levels")
        _set_fill(pdf, NAVY)
        _set_text(pdf, GOLD)
        pdf.set_font('Arial', 'B', 6)
        for comp in core_competencies:
            pdf.cell(23, 5, comp, border=0, fill=True, align='C')
        pdf.ln()

        _set_fill(pdf, SKY)
        _set_text(pdf, BLACK)
        pdf.set_font('Arial', '', 6)
        for comp in core_competencies:
            val = avg_level_map.get(comp, 0.0)
            
            pdf.cell(23, 5, str(round(val,2)) if val else "-", border=1, fill=True, align='C')
        pdf.ln(8)
        

        # ── Fee statement ──
        draw_section_title(pdf, "Fee Statement")
        fees = Fee.objects.filter(registration_no=student.registration_no, term=term)
        grade_obj = GradeFeeConfig.objects.filter(school_id=school_id, grade=student.grade).first()
        amount_billed = grade_obj.expected_fee if grade_obj else Decimal('0')
        amount_paid   = sum(f.amount for f in fees if f.amount)
        balance       = amount_billed - Decimal(amount_paid)

        fee_cols = [('Amount Billed',63),('Amount Paid',63),('Balance',63)]
        draw_styled_table_header(pdf, fee_cols)
        _set_text(pdf, BLACK)
        pdf.set_font('Arial', '', 8)
        pdf.cell(63, 6, str(amount_billed), border=1, align='C')
        pdf.cell(63, 6, str(amount_paid),   border=1, align='C')
        _set_text(pdf, CRIMSON if balance > 0 else GREEN)
        pdf.cell(63, 6, str(balance), border=1, align='C')
        pdf.ln(6)
        _set_text(pdf, BLACK)

        # ── Comments ──
        current_date = datetime.now().strftime("%d/%m/%Y")
        _set_draw(pdf, GOLD)
        pdf.set_line_width(0.6)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.set_line_width(0.2)
        _set_draw(pdf, BLACK)
        pdf.ln(4)
        pdf.set_font('Arial', 'B', 8)
        pdf.cell(0, 5, f'Closing Date: {current_date}', ln=True)
        pdf.ln(3)
        pdf.cell(0, 5, 'Class Teacher Comment: '+'.'*70, ln=True)
        pdf.ln(3)
        pdf.cell(0, 5, 'Guardian Comment: '+'.'*73, ln=True)
        pdf.ln(3)
        pdf.cell(0, 5, f'Date: {current_date}   H/T Sign & Stamp: '+'.'*40, ln=True)
        pdf_footer(pdf)

    resp = HttpResponse(pdf.output(dest="S").encode("latin1"), content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{grade} {stream} {term} report forms.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# SUMMATIVE REPORT FORMS (Opener, Mid, End Average)
# ─────────────────────────────────────────────────────────────────────────────

def _get_summative_level(score):
    if score is None: return {'level': '-', 'remark': '-'}
    if score >= 80: return {'level': 'EE', 'remark': 'Exceeding Expectations'}
    if score >= 60: return {'level': 'ME', 'remark': 'Meeting Expectations'}
    if score >= 40: return {'level': 'AE', 'remark': 'Approaching Expectations'}
    return {'level': 'BE', 'remark': 'Below Expectations'}

def _get_summative_report_data(school_id, term, year, grade=None, stream=None, registration_no=None):
    all_grade_marks = LearningAreaMark.objects.filter(school_id=school_id, year=year)
    if grade:
        all_grade_marks = all_grade_marks.filter(grade=grade)
        grade_students_qs = StudentInfo.objects.filter(school_id=school_id, grade=grade)
    else:
        if registration_no:
            student = StudentInfo.objects.filter(school_id=school_id, registration_no=registration_no).first()
            if student:
                grade = student.grade
                all_grade_marks = all_grade_marks.filter(grade=grade)
                grade_students_qs = StudentInfo.objects.filter(school_id=school_id, grade=grade)
            else:
                grade_students_qs = StudentInfo.objects.filter(school_id=school_id)
        else:
            grade_students_qs = StudentInfo.objects.filter(school_id=school_id)

    data_map = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {'Opener': None, 'Mid Term': None, 'End Term': None})))
    for m in all_grade_marks:
        data_map[m.student.registration_no][m.term][m.learning_area_id][m.exam_type] = m.marks

    comp_qs = LearnerCompetency.objects.filter(school_id=school_id, year=year)
    if grade: comp_qs = comp_qs.filter(grade=grade)
    if registration_no: comp_qs = comp_qs.filter(student__registration_no=registration_no)
    
    comp_map = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for c in comp_qs:
        comp_map[c.student.registration_no][c.term][c.subject][c.competency] = c.level

    learning_areas = {la.id: la.name for la in LearningArea.objects.filter(school_id=school_id)}
    student_stats = {} 
    
    for student in grade_students_qs:
        rn = student.registration_no
        terms_data = data_map.get(rn, {})
        subj_marks = terms_data.get(term, {})
        
        total_score = 0
        subjects_count = 0
        details = {}
        for la_id, scores in subj_marks.items():
            vals = [v for v in scores.values() if v is not None]
            if not vals: continue
            avg = sum(vals) / len(vals)
            total_score += avg
            subjects_count += 1
            lvl = _get_summative_level(avg)
            details[learning_areas.get(la_id, f'Subject {la_id}')] = {
                'Opener': scores.get('Opener'),
                'Mid Term': scores.get('Mid Term'),
                'End Term': scores.get('End Term'),
                'Average': avg,
                'Level': lvl['level'],
                'Remark': lvl['remark']
            }
        
        mean_current = total_score / subjects_count if subjects_count > 0 else 0
        
        historical = {}
        for t in ['Term 1', 'Term 2', 'Term 3']:
            t_subj_marks = terms_data.get(t, {})
            t_total = 0
            t_count = 0
            for la_id, t_scores in t_subj_marks.items():
                t_vals = [v for v in t_scores.values() if v is not None]
                if t_vals:
                    t_total += sum(t_vals) / len(t_vals)
                    t_count += 1
            historical[t] = round(t_total / t_count, 1) if t_count > 0 else 0

        term_comps = comp_map.get(rn, {}).get(term, {})
        agg_comp = defaultdict(list)
        for s_name, comps in term_comps.items():
            for c_name, c_lvl in comps.items():
                agg_comp[c_name].append(c_lvl)
        avg_comp_map = {c: sum(lvls)/len(lvls) for c, lvls in agg_comp.items()}

        student_stats[rn] = {
            'total': round(total_score, 2),
            'mean': round(mean_current, 2),
            'subjects': details,
            'historical': historical,
            'comp_map': term_comps,
            'avg_comp': avg_comp_map,
            'stream': student.stream,
            'student_obj': student
        }

    ranked_reg_nos = [rn for rn, stats in student_stats.items() if stats['subjects']]
    overall_sorted = sorted(ranked_reg_nos, key=lambda r: student_stats[r]['total'], reverse=True)
    overall_ranks = {}
    curr, prev_val = 1, None
    for idx, rn in enumerate(overall_sorted, 1):
        if prev_val is not None and student_stats[rn]['total'] != prev_val:
            curr = idx
        overall_ranks[rn] = curr
        prev_val = student_stats[rn]['total']

    stream_ranks = {}
    streams_found = set(student_stats[rn]['stream'] for rn in ranked_reg_nos)
    for s in streams_found:
        s_rn = [rn for rn in ranked_reg_nos if student_stats[rn]['stream'] == s]
        s_sorted = sorted(s_rn, key=lambda r: student_stats[r]['total'], reverse=True)
        curr, prev_val = 1, None
        for idx, rn in enumerate(s_sorted, 1):
            if prev_val is not None and student_stats[rn]['total'] != prev_val:
                curr = idx
            stream_ranks[rn] = curr
            prev_val = student_stats[rn]['total']

    return student_stats, overall_ranks, stream_ranks, ranked_reg_nos


def draw_term_performance_graph(pdf, historical_data, x_start=None):
    x_start = x_start or (pdf.l_margin + 12)
    y_base = pdf.get_y() + 28
    chart_h = 24
    chart_w = 70
    
    pdf.set_font('Arial', 'B', 8); _set_text(pdf, NAVY)
    pdf.text(x_start, pdf.get_y() + 4, "ACADEMIC PERFORMANCE TREND")
    
    _set_draw(pdf, (220, 220, 220))
    for i in range(0, 101, 25):
        y = y_base - (i * chart_h / 100)
        pdf.line(x_start, y, x_start + chart_w, y)
        pdf.set_font('Arial', '', 6); pdf.text(x_start - 8, y + 1, f"{i}%")
    
    terms = ['Term 1', 'Term 2', 'Term 3']
    bar_w = 12
    colors = [NAVY, GOLD, (100, 116, 139)]
    for i, t in enumerate(terms):
        val = historical_data.get(t, 0)
        h = val * chart_h / 100
        x = x_start + (i + 1) * (chart_w / 4) - (bar_w / 2)
        _set_fill(pdf, colors[i])
        pdf.rect(x, y_base - h, bar_w, h, style='F')
        _set_text(pdf, BLACK); pdf.set_font('Arial', 'B', 7); pdf.text(x - 2, y_base + 5, t)
        pdf.set_font('Arial', '', 6); pdf.text(x + 2, y_base - h - 2, f"{val}%")
    pdf.set_y(y_base + 10)

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def print_summative_report_forms(request):
    school_id = request.user.school_id
    messages.get_messages(request).used = True
    term = request.GET.get('term')
    grade = request.GET.get('grade')
    stream = request.GET.get('stream')
    year = request.GET.get('year', str(datetime.now().year))

    stats, o_ranks, s_ranks, reg_nos = _get_summative_report_data(school_id, term, year, grade, stream)
    
    if stream:
        reg_nos = [rn for rn in reg_nos if stats[rn]['stream'] == stream]

    pdf = PdfReportForm()
    if not reg_nos:
        pdf.add_page(); pdf_header(request, pdf, 30); pdf.set_font('Arial','I',12); pdf.cell(0,10,'No summative data found.',0,1,'C')
    
    for rn in reg_nos:
        s_data = stats[rn]
        student = s_data['student_obj']
        pdf.add_page(); pdf.add_background_color(245, 249, 255); pdf.add_watermark(student.first_name.upper())
        pdf_header(request, pdf, 30)
        _set_text(pdf, NAVY); pdf.set_font('Arial', 'BU', 13); pdf.cell(0, 6, 'SUMMATIVE EVALUATION REPORT', align='C', ln=True); pdf.ln(4)
        pdf.student_info_banner(rn, f"{student.first_name} {student.surname}", student.grade, student.stream, term)
        pdf.ln(3)

        # 1. Competency Breakdown by Learning Area
        draw_section_title(pdf, "Learning Area Competencies")
        col_w = (pdf.w - pdf.l_margin - pdf.r_margin - 35) / max(len(core_competencies), 1)
        _set_fill(pdf, NAVY); _set_text(pdf, GOLD); pdf.set_font('Arial', 'B', 4.5)
        pdf.cell(35, 5, 'Learning Area', border=0, fill=True, align='C')
        for comp in core_competencies:
            pdf.cell(col_w, 5, comp, border=0, fill=True, align='C')
        pdf.ln()
        for i, subj in enumerate(s_data['subjects'].keys()):
            fill = SKY if i % 2 == 0 else WHITE; _set_fill(pdf, fill); _set_text(pdf, BLACK); pdf.set_font('Arial', '', 4.5)
            pdf.cell(35, 4, subj, border=1, fill=True, align='L')
            for comp in core_competencies:
                val = s_data['comp_map'].get(subj, {}).get(comp)
                pdf.cell(col_w, 4, str(round(val,1)) if val else "-", border=1, fill=True, align='C')
            pdf.ln()
        pdf.ln(3)

        # 2. Performance Table
        draw_section_title(pdf, "Learning Area Marks")
        cols = [('Learning Area',42),('Opener',20),('Mid Term',20),('End Term',20),('Average',20),('Level',18),('Remark',40)]
        draw_styled_table_header(pdf, cols)
        for i, (subj, m) in enumerate(s_data['subjects'].items()):
            row = [subj, m['Opener'] or '-', m['Mid Term'] or '-', m['End Term'] or '-', round(m['Average'],1), m['Level'], m['Remark']]
            draw_styled_row(pdf, row, [w for _,w in cols], i, ['L','C','C','C','C','C','C'], h=5)
        
        pdf.ln(3)
        _set_fill(pdf, NAVY); pdf.rect(pdf.l_margin, pdf.get_y(), 180, 8, style='F')
        _set_text(pdf, GOLD); pdf.set_font('Arial', 'B', 8); pdf.set_x(pdf.l_margin)
        pdf.cell(36, 8, f"Total: {s_data['total']}", 0, 0, 'C')
        pdf.cell(36, 8, f"Mean: {s_data['mean']}", 0, 0, 'C')
        pdf.cell(36, 8, f"Stream Pos: {s_ranks.get(rn,'-')}", 0, 0, 'C')
        pdf.cell(36, 6, f"Overall Pos: {o_ranks.get(rn,'-')}", 0, 0, 'C')
        pdf.ln(8)

        # 3. Aggregated Competency
        draw_section_title(pdf, "Aggregated Competency Levels")
        _set_fill(pdf, NAVY); _set_text(pdf, GOLD); pdf.set_font('Arial', 'B', 5.5)
        for comp in core_competencies: pdf.cell(23, 5, comp, border=0, fill=True, align='C')
        pdf.ln(); _set_fill(pdf, SKY); _set_text(pdf, BLACK); pdf.set_font('Arial', '', 5.5)
        for comp in core_competencies:
            val = s_data['avg_comp'].get(comp)
            pdf.cell(23, 4, str(round(val,1)) if val else "-", border=1, fill=True, align='C')
        pdf.ln(6)

        # 4. Fee & Graph row (Side-by-Side)
        curr_y = pdf.get_y()
        # Fee box (Left)
        draw_section_title(pdf, "Fee Statement", w=90)
        grade_obj = GradeFeeConfig.objects.filter(grade=student.grade, school_id=school_id).first()
        billed = grade_obj.expected_fee if grade_obj else Decimal('0')
        paid = Fee.objects.filter(registration_no_id=rn, term=term, year=year).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
        balance = billed - paid
        draw_styled_table_header(pdf, [('Billed',30),('Paid',30),('Balance',30)])
        pdf.set_font('Arial', '', 7)
        pdf.cell(30, 5, str(billed), 1, 0, 'C'); pdf.cell(30, 5, str(paid), 1, 0, 'C')
        _set_text(pdf, CRIMSON if balance > 0 else GREEN); pdf.cell(30, 5, str(balance), 1, 1, 'C'); _set_text(pdf, BLACK)
        
        # Graph box (Right)
        pdf.set_xy(pdf.l_margin + 105, curr_y)
        draw_term_performance_graph(pdf, s_data['historical'], x_start=pdf.l_margin + 105)
        pdf.ln(8)

        draw_section_title(pdf, "Comments")
        pdf.set_font('Arial','B',8); _set_text(pdf, BLACK)
        pdf.cell(0, 5, f'Class Teacher: '+' .'*40, ln=True); pdf.ln(2)
        pdf.cell(0, 5, f'Head Teacher: '+' .'*41, ln=True); pdf.ln(4)
        pdf_footer(pdf)

    resp = HttpResponse(pdf.output(dest="S").encode("latin1"), content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="Summative_Reports_{term}.pdf"'
    return resp


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def print_individual_summative_report_form(request):
    school_id = request.user.school_id
    registration_no = request.GET.get('registration_no') or request.user.registration_no
    term = request.GET.get('term')
    year = request.GET.get('year', str(datetime.now().year))

    stats, o_ranks, s_ranks, ranked_reg_nos = _get_summative_report_data(school_id, term, year, registration_no=registration_no)
    
    if registration_no not in stats:
        return HttpResponse("No marks found for this student.", status=400)

    s_data = stats[registration_no]
    student = s_data['student_obj']

    pdf = PdfReportForm()
    pdf.add_page(); pdf.add_background_color(245, 249, 255); pdf.add_watermark(student.first_name.upper())
    pdf_header(request, pdf, 30)
    _set_text(pdf, NAVY); pdf.set_font('Arial', 'BU', 13); pdf.cell(0, 6, 'SUMMATIVE EVALUATION REPORT', align='C', ln=True); pdf.ln(4)
    pdf.student_info_banner(registration_no, f"{student.first_name} {student.surname}", student.grade, student.stream, term)
    pdf.ln(3)

    # 1. Competency Breakdown by Learning Area
    draw_section_title(pdf, "Learning Area Competencies")
    col_w = (pdf.w - pdf.l_margin - pdf.r_margin - 35) / max(len(core_competencies), 1)
    _set_fill(pdf, NAVY); _set_text(pdf, GOLD); pdf.set_font('Arial', 'B', 4.5)
    pdf.cell(35, 5, 'Learning Area', border=0, fill=True, align='C')
    for comp in core_competencies:
        pdf.cell(col_w, 5, comp, border=0, fill=True, align='C')
    pdf.ln()
    for i, subj in enumerate(s_data['subjects'].keys()):
        fill = SKY if i % 2 == 0 else WHITE; _set_fill(pdf, fill); _set_text(pdf, BLACK); pdf.set_font('Arial', '', 4.5)
        pdf.cell(35, 4, subj, border=1, fill=True, align='L')
        for comp in core_competencies:
            val = s_data['comp_map'].get(subj, {}).get(comp)
            pdf.cell(col_w, 4, str(round(val,1)) if val else "-", border=1, fill=True, align='C')
        pdf.ln()
    pdf.ln(3)

    # 2. Performance Table
    draw_section_title(pdf, "Learning Area Marks")
    cols = [('Learning Area',42),('Opener',20),('Mid Term',20),('End Term',20),('Average',20),('Level',18),('Remark',40)]
    draw_styled_table_header(pdf, cols)
    for i, (subj, m) in enumerate(s_data['subjects'].items()):
        row = [subj, m['Opener'] or '-', m['Mid Term'] or '-', m['End Term'] or '-', round(m['Average'],1), m['Level'], m['Remark']]
        draw_styled_row(pdf, row, [w for _,w in cols], i, ['L','C','C','C','C','C','C'], h=5)
    
    pdf.ln(3)
    _set_fill(pdf, NAVY); pdf.rect(pdf.l_margin, pdf.get_y(), 180, 8, style='F')
    _set_text(pdf, GOLD); pdf.set_font('Arial', 'B', 8); pdf.set_x(pdf.l_margin)
    pdf.cell(45, 8, f"Total: {s_data['total']}", 0, 0, 'C')
    pdf.cell(45, 8, f"Mean: {s_data['mean']}", 0, 0, 'C')
    pdf.cell(45, 8, f"Stream Pos: {s_ranks.get(registration_no,'-')}", 0, 0, 'C')
    pdf.cell(45, 6, f"Overall Pos: {o_ranks.get(registration_no,'-')}", 0, 0, 'C')
    pdf.ln(8)

    # 3. Aggregated Competency
    draw_section_title(pdf, "Aggregated Competency Levels")
    _set_fill(pdf, NAVY); _set_text(pdf, GOLD); pdf.set_font('Arial', 'B', 5.5)
    for comp in core_competencies: pdf.cell(23, 5, comp, border=0, fill=True, align='C')
    pdf.ln(); _set_fill(pdf, SKY); _set_text(pdf, BLACK); pdf.set_font('Arial', '', 5.5)
    for comp in core_competencies:
        val = s_data['avg_comp'].get(comp)
        pdf.cell(23, 4, str(round(val,1)) if val else "-", border=1, fill=True, align='C')
    pdf.ln(6)

    # 4. Fee & Graph row (Side-by-Side)
    curr_y = pdf.get_y()
    # Fee box (Left)
    draw_section_title(pdf, "Fee Statement", w=90)
    grade_obj = GradeFeeConfig.objects.filter(grade=student.grade, school_id=school_id).first()
    billed = grade_obj.expected_fee if grade_obj else Decimal('0')
    paid = Fee.objects.filter(registration_no_id=registration_no, term=term, year=year).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
    balance = billed - paid
    draw_styled_table_header(pdf, [('Billed',30),('Paid',30),('Balance',30)])
    pdf.set_font('Arial', '', 7)
    pdf.cell(30, 5, str(billed), 1, 0, 'C'); pdf.cell(30, 5, str(paid), 1, 0, 'C')
    _set_text(pdf, CRIMSON if balance > 0 else GREEN); pdf.cell(30, 5, str(balance), 1, 1, 'C'); _set_text(pdf, BLACK)
    
    # Graph box (Right)
    pdf.set_xy(pdf.l_margin + 105, curr_y)
    draw_term_performance_graph(pdf, s_data['historical'], x_start=pdf.l_margin + 105)
    pdf.ln(8)

    draw_section_title(pdf, "Comments")
    pdf.set_font('Arial','B',8); _set_text(pdf, BLACK)
    pdf.cell(0, 5, f'Class Teacher: '+' .'*40, ln=True); pdf.ln(2)
    pdf.cell(0, 5, f'Head Teacher: '+' .'*41, ln=True); pdf.ln(4)
    pdf_footer(pdf)

    resp = HttpResponse(pdf.output(dest="S").encode("latin1"), content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="Summative_Report_{registration_no}.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# INDIVIDUAL REPORT FORM
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def print_individual_report_form(request):
    school_id    = request.user.school_id
    registration_no = request.user.registration_no
    term  = request.GET.get('term', '')
    year  = request.GET.get('year', str(datetime.now().year))

    if not registration_no or not term:
        return HttpResponse("Missing registration number or term.", status=400)

    student = get_object_or_404(StudentInfo, school_id=school_id, registration_no=registration_no)
    grade   = student.grade

    # marks
    marks_qs = SubStrandMark.objects.filter(
        student__registration_no=registration_no, term=term, year=year,
        sub_strand__strand__grade=grade)
    subject_averages = marks_qs.values('sub_strand__strand__subject').annotate(
        avg_level=Avg('level'), avg_score=Avg('score'),
        project_score=Avg('level', filter=Q(assessement_type='SBA-Project')),
        practical_score=Avg('level', filter=Q(assessement_type='SBA-Practical')),
        written_score=Avg('level', filter=Q(assessement_type='SBA-Written')),
        total_items=Count('id'),
    ).filter(total_items__gt=0)

    subject_data = defaultdict(lambda: {'level':None,'score':None,'project':None,'practical':None,'written':None})
    for rec in subject_averages:
        s = rec['sub_strand__strand__subject']
        subject_data[s].update(level=rec['avg_level'], score=rec['avg_score'],
                               project=rec['project_score'], practical=rec['practical_score'],
                               written=rec['written_score'])

    subjects_in_grade = marks_qs.values_list('sub_strand__strand__subject', flat=True).distinct()
    levels = [d['level'] for d in subject_data.values() if d['level'] is not None]
    scores = [d['score'] for d in subject_data.values() if d['score'] is not None]
    overall_level = round(sum(levels)/len(levels), 2) if levels else 0
    overall_score = round(sum(scores)/len(scores), 2) if scores else 0

    # competency
    comp_qs = LearnerCompetency.objects.filter(student=student, term=term, year=year).values('subject','competency','level')
    comp_map = defaultdict(dict)
    for c in comp_qs:
        comp_map[c['subject']][c['competency']] = c['level']
    competency_summary = LearnerCompetency.objects.filter(
        student__registration_no=registration_no, term=term, year=year
    ).values('competency').annotate(avg_level=Avg('level')).order_by('competency')
    avg_level_map = {i['competency']: i['avg_level'] for i in competency_summary}

    # ── PDF ──────────────────────────────────────────────────────────────────
    pdf = PdfReportForm()
    pdf.add_page()
    pdf.add_background_color(245, 249, 255)
    pdf.add_watermark(student.first_name.upper())
    pdf.set_text_color(0, 0, 0)
    pdf_header(request, pdf, 30)

    _set_text(pdf, NAVY)
    pdf.set_font('Arial', 'BU', 13)
    pdf.cell(0, 6, 'LEARNER COMPETENCY REPORT', align='C', ln=True)
    pdf.ln(4)

    full_name = f"{student.first_name} {student.second_name or ''} {student.surname or ''}".strip()
    pdf.student_info_banner(registration_no, full_name, grade, student.stream, term)
    pdf.ln(4)

    # Learning area table
    draw_section_title(pdf, "Learning Area Performance")
    la_cols = [
        ('Learning Area',40),('SBA-Proj',18),('SBA-Prac',18),('SBA-Writ',18),
        ('Avg Score',18),('Avg Level',18),('CBC Level',18),('Remark',30),
    ]
    draw_styled_table_header(pdf, la_cols)
    for row_idx, subj in enumerate(subjects_in_grade):
        data = subject_data.get(subj, {})
        rep  = get_cbc_level_and_remark(data.get('level'))
        draw_styled_row(pdf, [
            subj,
            f"{round(data.get('project'),1)}" if data.get('project') is not None else "-",
            f"{round(data.get('practical'),1)}" if data.get('practical') is not None else "-",
            f"{round(data.get('written'),1)}" if data.get('written') is not None else "-",
            f"{round(data.get('score'),1)}" if data.get('score') is not None else "-",
            f"{round(data.get('level'),2)}" if data.get('level') is not None else "-",
            rep['level'], rep['remark'],
        ], [w for _,w in la_cols], row_idx, ['L','C','C','C','C','C','C','C'])

    pdf.ln(3)

    # Summary strip
    _set_fill(pdf, NAVY)
    pdf.rect(pdf.l_margin, pdf.get_y(), 95, 8, style='F')
    _set_text(pdf, GOLD)
    pdf.set_font('Arial', 'B', 8)
    pdf.set_x(pdf.l_margin)
    pdf.cell(47.5, 8, f"Avg Level: {overall_level}", align='C')
    pdf.cell(47.5, 8, f"Avg Score: {overall_score}%", align='C')
    pdf.ln(10)
    _set_text(pdf, BLACK)

    # Competency breakdown
    draw_section_title(pdf, "Competency Breakdown by Learning Area")
    col_w = (pdf.w - pdf.l_margin - pdf.r_margin - 35) / max(len(core_competencies), 1)
    _set_fill(pdf, NAVY)
    _set_text(pdf, GOLD)
    pdf.set_font('Arial', 'B', 5)
    pdf.cell(35, 6, 'Learning Area', border=0, fill=True, align='C')
    for comp in core_competencies:
        pdf.cell(col_w, 6, comp, border=0, fill=True, align='C')
    pdf.ln()

    for row_idx, subj in enumerate(subjects_in_grade):
        fill = SKY if row_idx % 2 == 0 else WHITE
        _set_fill(pdf, fill)
        _set_text(pdf, BLACK)
        pdf.set_font('Arial', '', 5)
        pdf.cell(35, 5, subj, border=1, fill=True, align='L')
        for comp in core_competencies:
            val = comp_map.get(subj, {}).get(comp)
            pdf.cell(col_w, 5, str(round(val,1)) if val else "-", border=1, fill=True, align='C')
        pdf.ln()

    pdf.ln(4)

    # Aggregated competency
    draw_section_title(pdf, "Aggregated Competency Levels")
    _set_fill(pdf, NAVY)
    _set_text(pdf, GOLD)
    pdf.set_font('Arial', 'B', 6)
    for comp in core_competencies:
        pdf.cell(23, 5, comp, border=0, fill=True, align='C')
    pdf.ln()
    _set_fill(pdf, SKY)
    _set_text(pdf, BLACK)
    pdf.set_font('Arial', '', 6)
    for comp in core_competencies:
        val = avg_level_map.get(comp, 0.0)
        pdf.cell(23, 5, str(round(val,2)) if val else "-", border=1, fill=True, align='C')
    pdf.ln(8)

    # Fee section
    draw_section_title(pdf, "Fee Statement")
    grade_obj     = GradeFeeConfig.objects.filter(grade=grade, school_id=school_id).first()
    amount_billed = grade_obj.expected_fee if grade_obj else Decimal('0')
    fees_agg      = Fee.objects.filter(registration_no=registration_no, term=term).aggregate(Sum('amount'))
    paid          = fees_agg['amount__sum'] or Decimal('0')
    balance       = amount_billed - paid

    draw_styled_table_header(pdf, [('Billed',63),('Paid',63),('Balance',63)])
    pdf.set_font('Arial', '', 8)
    _set_text(pdf, BLACK)
    pdf.cell(63, 6, str(amount_billed), border=1, align='C')
    pdf.cell(63, 6, str(paid), border=1, align='C')
    _set_text(pdf, CRIMSON if balance > 0 else GREEN)
    pdf.cell(63, 6, str(balance), border=1, align='C')
    pdf.ln(6)
    _set_text(pdf, BLACK)

    # Comments
    current_date = datetime.now().strftime("%d/%m/%Y")
    _set_draw(pdf, GOLD)
    pdf.set_line_width(0.6)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.set_line_width(0.2)
    _set_draw(pdf, BLACK)
    pdf.ln(4)
    pdf.set_font('Arial', 'B', 8)
    pdf.cell(0, 5, f'Closing Date: {current_date}', ln=True)
    pdf.ln(3)
    pdf.cell(0, 5, 'Class Teacher Comment: '+'.'*70, ln=True)
    pdf.ln(3)
    pdf.cell(0, 5, 'Guardian Comment: '+'.'*73, ln=True)
    pdf.ln(5)
    pdf.cell(0, 5, f'Date: {current_date}   H/T Sign & Stamp: '+'.'*40, ln=True)
    pdf_footer(pdf)

    resp = HttpResponse(pdf.output(dest="S").encode('latin1'), content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="{registration_no}_{term}_report.pdf"'
    return resp



# ─────────────────────────────────────────────────────────────────────────────
# FEE RECEIPT  (single)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def print_fee_reciept(request, fee_id):
    school_id = request.user.school_id
    messages.get_messages(request).used = True

    date = datetime.now()
    current_date = date.strftime("%d/%m/%Y")
    current_time = date.strftime("%H:%M:%S")

    fee          = get_object_or_404(Fee.objects.filter(school_id=school_id), id=fee_id)
    personal     = fee.registration_no
    grade_fee    = get_object_or_404(GradeFeeConfig.objects.filter(school_id=school_id), grade=personal.grade)
    expected_fee = Decimal(grade_fee.expected_fee or 0)
    all_payments = Fee.objects.filter(school_id=school_id, registration_no=personal.registration_no, term=fee.term)
    total_paid   = sum(Decimal(p.amount or 0) for p in all_payments)
    balance      = expected_fee - total_paid

    pdf = PdfReciept()
    pdf.add_page()
    pdf.add_background_color()
    pdf.add_watermark(personal.first_name.upper())
    pdf.set_text_color(0, 0, 0)
    pdf.add_header(request)

    # Title
    _set_text(pdf, NAVY)
    pdf.set_font("Arial", "BU", 9)
    pdf.cell(0, 6, "FEE PAYMENT RECEIPT", align="C", ln=True)
    pdf.ln(4)

    # Student info
    draw_section_title(pdf, "Student Details", w=pdf.w - pdf.l_margin - pdf.r_margin)
    pdf.info_pair("Reg No:",  personal.registration_no)
    full = f"{personal.first_name} {personal.second_name or ''} {personal.surname or ''}".strip()
    pdf.info_pair("Name:",    full)
    pdf.info_pair("Grade:",   personal.grade)
    pdf.info_pair("Stream:",  personal.stream)
    pdf.info_pair("Term:",    fee.term)
    pdf.info_pair("Date:",    str(fee.date_of_payment or current_date))
    pdf.ln(4)

    # Fee table
    draw_section_title(pdf, "Payment Summary", w=pdf.w - pdf.l_margin - pdf.r_margin)
    pdf.fee_summary_table(expected_fee, fee.amount, total_paid, balance)
    pdf.ln(8)

    # Footer strip
    _set_fill(pdf, GREY)
    pdf.rect(pdf.l_margin, pdf.get_y(), pdf.w - pdf.l_margin - pdf.r_margin, 8, style='F')
    _set_text(pdf, MID)
    pdf.set_font("Arial", "", 6)
    pdf.set_x(pdf.l_margin)
    pdf.cell(pdf.w - pdf.l_margin - pdf.r_margin, 8,
             f"H/T SIGN & STAMP ........................  Date: {current_date}", align='C')
    pdf.ln()
    pdf_footer(pdf)

    resp = HttpResponse(pdf.output(dest="S").encode("latin1"), content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{personal.registration_no}_fee_receipt.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# ATTENDANCE SHEET
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def print_attendance_sheet(request):
    school_id = request.user.school_id
    messages.get_messages(request).used = True

    grade  = request.GET.get('grade', '')
    stream = request.GET.get('stream', '')
    term   = request.GET.get('term', '')
    registration_no = request.GET.get('registration_no', '')

    students_qs = StudentInfo.objects.filter(school_id=school_id)
    if grade:  students_qs = students_qs.filter(grade=grade)
    if stream: students_qs = students_qs.filter(stream=stream)
    if registration_no: students_qs = students_qs.filter(registration_no=registration_no)
    students = list(students_qs.order_by('registration_no'))

    attendance_qs = StudentAttendance.objects.filter(school_id=school_id)
    if grade or stream:
        attendance_qs = attendance_qs.filter(registration_no__in=students)
    if term:
        attendance_qs = attendance_qs.filter(term=term)
    att_map = {}
    for a in attendance_qs:
        att_map.setdefault(a.registration_no, []).append(a)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf_header(request, pdf, 30)

    draw_section_title(pdf, f"Attendance Sheet  -  Grade: {grade or 'All'}   Stream: {stream or 'All'}   Term: {term or 'All'}")

    cols = [('Reg No',28),('Name',60),('Grade',18),('Stream',18),('Date(s) Present',52),('Term',14)]
    draw_styled_table_header(pdf, cols)

    for row_idx, student in enumerate(students):
        name    = " ".join(p for p in [student.first_name, student.second_name, student.surname] if p)
        records = att_map.get(student.registration_no, [])
        dates   = ", ".join(r.date_of_attendance.strftime('%d/%m') for r in records) if records else "-"
        draw_styled_row(pdf,
            [student.registration_no, name or "Unknown", student.grade, student.stream, dates, term or "-"],
            [28, 60, 18, 18, 52, 14], row_idx, ['L','L','C','C','L','C'])

    pdf_footer(pdf)
    safe = lambda s, d: (s.replace(' ','_') if s else d)
    resp = HttpResponse(pdf.output(dest="S").encode("latin1"), content_type="application/pdf")
    resp['Content-Disposition'] = f'attachment; filename="attendance_{safe(grade,"all")}_{safe(stream,"all")}_{safe(term,"all")}.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# ALL FEE RECEIPTS (bulk)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def print_all_fee_reciepts(request):
    school_id = request.user.school_id
    messages.get_messages(request).used = True
    current_date = datetime.now().strftime("%d/%m/%Y")

    grade         = request.GET.get('grade')
    stream        = request.GET.get('stream')
    selected_term = request.GET.get('term')

    students_query = StudentInfo.objects.filter(grade=grade, stream=stream, school_id=school_id)
    fee_filters = Q(school_id=school_id)
    if selected_term:
        fee_filters &= Q(term=selected_term)
    students = students_query.filter(
        registration_no__in=Fee.objects.filter(fee_filters).values_list('registration_no', flat=True).distinct()
    )

    pdf = PdfReciept()
    pdf.set_auto_page_break(auto=True, margin=15)

    if not students.exists():
        pdf.add_page()
        pdf_header(request, pdf, 30)
        pdf.set_font('Arial', 'I', 11)
        pdf.cell(0, 10, f'No fee records found for Grade {grade}, Stream {stream}', align='C')
    else:
        for student in students:
            term_query = Fee.objects.filter(school_id=school_id, registration_no=student.registration_no)
            if selected_term:
                term_query = term_query.filter(term=selected_term)
            terms = term_query.values_list('term', flat=True).distinct()

            for term in terms:
                all_payments = Fee.objects.filter(
                    school_id=school_id, registration_no=student.registration_no, term=term
                ).order_by('date_of_payment', 'time')
                total_paid   = sum(Decimal(p.amount) for p in all_payments)
                grade_fee    = get_object_or_404(Grade, school_id=school_id, name=student.grade)
                expected_fee = Decimal(grade_fee.expected_fee)
                balance      = expected_fee

                pdf.add_page()
                pdf.add_background_color()
                pdf.add_watermark(student.first_name.upper())
                pdf.set_text_color(0, 0, 0)
                pdf.add_header(request)

                _set_text(pdf, NAVY)
                pdf.set_font('Arial', 'BU', 8)
                pdf.cell(0, 5, 'FEE PAYMENT STATEMENT', align='C', ln=True)
                pdf.ln(3)

                draw_section_title(pdf, "Student Details", w=pdf.w - pdf.l_margin - pdf.r_margin)
                pdf.info_pair("Reg No:",  student.registration_no)
                pdf.info_pair("Name:",    f"{student.first_name} {student.second_name} {student.surname}")
                pdf.info_pair("Grade:",   student.grade)
                pdf.info_pair("Stream:",  student.stream)
                pdf.info_pair("Term:",    term)
                pdf.ln(3)

                draw_section_title(pdf, "Payment History", w=pdf.w - pdf.l_margin - pdf.r_margin)
                pay_cols = [('Mode',18),('Amount',20),('Balance',18),('Date',18),('Time',16)]
                draw_styled_table_header(pdf, pay_cols)
                for p_idx, payment in enumerate(all_payments):
                    balance -= Decimal(payment.amount)
                    draw_styled_row(pdf, [
                        payment.mode_of_payment, payment.amount, balance,
                        payment.date_of_payment.strftime("%d/%m/%Y"),
                        payment.time.strftime("%H:%M:%S"),
                    ], [18,20,18,18,16], p_idx, ['L','C','C','C','C'])

                pdf.ln(5)
                pdf.set_font('Arial', '', 6)
                _set_text(pdf, MID)
                pdf.cell(0, 6, f'H/T SIGN & STAMP: .......................   Date: {current_date}', ln=True)

                school = get_object_or_404(MasterSchool, id=school_id)
                pdf_footer(pdf, getattr(school, 'vision', ''))

    resp = HttpResponse(pdf.output(dest="S").encode('latin1'), content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="{grade}_{stream}_fee_statements.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# LEAVE RECEIPT  (single)
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def print_leave_receipt(request, leave_id):
    school_id = request.user.school_id
    messages.get_messages(request).used = True

    leave_data = get_object_or_404(LeaveManagement.objects.filter(school_id=school_id), id=leave_id)
    student    = leave_data.registration_no

    all_payments = Fee.objects.filter(school_id=school_id, registration_no=student.registration_no, term=leave_data.term)
    total_paid   = sum((p.amount or Decimal('0')) for p in all_payments)
    grade_obj    = Grade.objects.filter(school_id=school_id, name=student.grade).first()
    total_fees   = grade_obj.expected_fee if grade_obj and grade_obj.expected_fee else Decimal('0')
    balance      = total_fees - Decimal(total_paid)

    date = datetime.now()
    current_date = date.strftime("%d/%m/%Y")
    current_time = date.strftime("%H:%M:%S")

    pdf = PdfReciept()
    pdf.add_page()
    pdf.add_background_color()
    pdf.add_watermark(student.first_name.upper())
    pdf.set_text_color(0, 0, 0)
    pdf.add_header(request)

    _set_text(pdf, NAVY)
    pdf.set_font('Arial', 'BU', 10)
    pdf.cell(0, 6, 'LEAVE OUT RECEIPT', align='C', ln=True)
    pdf.ln(4)

    draw_section_title(pdf, "Student Details", w=pdf.w - pdf.l_margin - pdf.r_margin)
    pdf.info_pair("Reg No:", student.registration_no)
    pdf.info_pair("Name:",   f"{student.first_name} {student.second_name} {student.surname}")
    pdf.info_pair("Grade:",  student.grade)
    pdf.info_pair("Stream:", student.stream)
    pdf.info_pair("Term:",   leave_data.term)
    pdf.info_pair("Date:",   str(leave_data.date_of_leave or current_date))
    pdf.ln(4)

    # Confirmation text
    _set_fill(pdf, SKY)
    pdf.rect(pdf.l_margin, pdf.get_y(), pdf.w - pdf.l_margin - pdf.r_margin, 12, style='F')
    _set_text(pdf, NAVY)
    pdf.set_font('Arial', 'I', 6)
    pdf.set_x(pdf.l_margin + 2)
    pdf.multi_cell(pdf.w - pdf.l_margin - pdf.r_margin - 4, 4,
                   "This is a confirmation receipt that the student named above has been granted permission to leave school premises.", align='C')
    pdf.ln(4)

    draw_section_title(pdf, "Leave Details", w=pdf.w - pdf.l_margin - pdf.r_margin)
    draw_styled_table_header(pdf, [('Reason For Leave', 45), ('Details', 45)])
    if leave_data.reason == 'School Fees':
        draw_styled_row(pdf, ['School Fees', f'Balance: {balance}'], [45, 45], 0, ['L','L'])
    else:
        draw_styled_row(pdf, ['Other', str(leave_data.other_reason or '-')], [45, 45], 0, ['L','L'])

    pdf.ln(8)
    _set_text(pdf, MID)
    pdf.set_font('Arial', '', 6)
    pdf.cell(0, 6, f'H/T SIGN & STAMP .......................   Date: {current_date}', ln=True)

    school = MasterSchool.objects.filter(id=school_id).first()
    pdf_footer(pdf, getattr(school, 'vision', '') if school else '')

    resp = HttpResponse(pdf.output(dest='S').encode('latin1'), content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="leave_receipt_{leave_id}.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# LEAVE REPORT
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def generate_leave_report(request):
    school_id   = request.user.school_id
    report_type = request.GET.get('report_type', 'Leave Summary Report')
    start_date  = request.GET.get('start_date')
    end_date    = request.GET.get('end_date')
    out_format  = (request.GET.get('export_format') or request.GET.get('format') or 'pdf').lower()

    def parse_date(s):
        try: return datetime.strptime(s, '%Y-%m-%d').date() if s else None
        except: return None

    start = parse_date(start_date)
    end   = parse_date(end_date)

    leaves_qs = LeaveManagement.objects.filter(school_id=school_id).select_related('registration_no').order_by('-date_of_leave')
    if start: leaves_qs = leaves_qs.filter(date_of_leave__gte=start)
    if end:   leaves_qs = leaves_qs.filter(date_of_leave__lte=end)
    if report_type == 'Pending Approvals Report':
        leaves_qs = leaves_qs.filter(Q(status__isnull=True)|Q(status__exact='')|Q(status__iexact='pending'))

    date_range_label = f"{start.strftime('%d/%m/%Y') if start else 'Start'} to {end.strftime('%d/%m/%Y') if end else 'Now'}"

    if out_format in ['csv','excel']:
        sio = io.StringIO()
        w = csv.writer(sio)
        w.writerow(['Date Applied','Student Reg No','Student Name','Grade','Reason','Start Date','End Date','Status'])
        for leave in leaves_qs:
            s = leave.registration_no
            w.writerow([leave.date_of_leave, s.registration_no,
                        f"{getattr(s,'first_name','')} {getattr(s,'surname','')}".strip(),
                        getattr(s,'grade',''), leave.reason,
                        leave.date_of_leave, leave.return_date, leave.status or 'Pending'])
        content      = sio.getvalue().encode('utf-8')
        content_type = 'text/csv' if out_format == 'csv' else 'application/vnd.ms-excel'
        filename     = f"leave_report_{datetime.now().date()}.csv"
    else:
        pdf = FPDF(orientation='L')
        pdf.add_page()
        pdf_header(request, pdf, 30)
        draw_section_title(pdf, f"{report_type}  |  Period: {date_range_label}")

        cols = [('Reg No',25),('Name',60),('Grade',20),('Reason',40),('Start Date',30),('End Date',30),('Status',30)]
        draw_styled_table_header(pdf, cols)
        for idx, leave in enumerate(leaves_qs):
            s    = leave.registration_no
            name = f"{getattr(s,'first_name','')} {getattr(s,'surname','')}".strip()
            draw_styled_row(pdf, [
                s.registration_no, name[:28], getattr(s,'grade',''),
                str(leave.reason or 'Other')[:20],
                str(leave.date_of_leave or '-'), str(leave.return_date or '-'),
                str(leave.status or 'Pending').capitalize(),
            ], [w for _,w in cols], idx, ['L','L','C','L','C','C','C'])

        pdf_footer(pdf)
        content      = pdf.output(dest='S').encode('latin1')
        content_type = 'application/pdf'
        filename     = f"leave_report_{datetime.now().date()}.pdf"

    resp = HttpResponse(content, content_type=content_type)
    resp['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# FEE REPORT
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def generate_fee_report(request):
    school_id   = request.user.school_id
    report_type = request.GET.get('reportType', '')
    period      = request.GET.get('period')
    start_date  = request.GET.get('start_date')
    end_date    = request.GET.get('end_date')
    out_format  = (request.GET.get('export_format') or request.GET.get('format') or 'pdf').lower()
    def parse_date(s):
        try: return datetime.strptime(s, '%Y-%m-%d').date() if s else None
        except: return None

    start = parse_date(start_date)
    grade = request.GET.get('grade', '')
    stream = request.GET.get('stream', '')
    
    fees_qs = Fee.objects.filter(school_id=school_id).select_related('registration_no').order_by('-date_of_payment','-time')
    
    if grade:
        fees_qs = fees_qs.filter(registration_no__grade=grade)
    if stream:
        fees_qs = fees_qs.filter(registration_no__stream=stream)

    if report_type == 'monthly-collection' and start:
        fees_qs = fees_qs.filter(date_of_payment__month=start.month, date_of_payment__year=start.year)
    elif report_type == 'payment-mode':
        fees_qs = fees_qs.filter(mode_of_payment__in=['M-Pesa','Cash','Bank Transfer'])
    elif period == 'daily' and start:
        fees_qs = fees_qs.filter(date_of_payment=start)

    pdf = FPDF()
    pdf.add_page()
    pdf_header(request, pdf, 30)
    draw_section_title(pdf, f"Fee Report  -  {report_type or 'All'}")

    cols = [('Reg No',25),('Name',50),('Grade',20),('Stream',20),('Mode',25),('Term',25),('Amount',30)]
    draw_styled_table_header(pdf, cols)

    for idx, fee in enumerate(fees_qs):
        draw_styled_row(pdf, [
            fee.registration_no.registration_no,
            f"{fee.registration_no.first_name} {fee.registration_no.surname}",
            fee.registration_no.grade, fee.registration_no.stream,
            fee.mode_of_payment, fee.term, f"{fee.amount:,}",
        ], [w for _,w in cols], idx, ['L','L','C','C','C','C','R'])

    pdf.ln(4)
    total_amount = fees_qs.aggregate(Sum('amount'))['amount__sum'] or 0
    _set_fill(pdf, NAVY)
    _set_text(pdf, GOLD)
    pdf.set_font('Arial', 'B', 10)
    tw = sum(w for _,w in cols)
    pdf.rect(pdf.l_margin, pdf.get_y(), tw, 8, style='F')
    pdf.set_x(pdf.l_margin)
    pdf.cell(tw, 8, f"TOTAL COLLECTED:  Ksh {total_amount:,}", align='R')
    pdf.ln(10)
    _set_text(pdf, BLACK)
    pdf_footer(pdf)
    resp = HttpResponse(pdf.output(dest="S").encode('latin1'), content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="fee_report_{datetime.now().date()}.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC FEE RECORDS REPORT
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def generate_fee_records_report(request):
    school_id = request.GET.get('school_id') or None
    if request.user and getattr(request.user, 'is_authenticated', False):
        school_id = getattr(request.user, 'school_id', school_id)
    if not school_id:
        return HttpResponse("Missing school_id.", status=400)

    report_type = request.GET.get('report_type', 'Fee Records')
    period      = request.GET.get('period')
    term        = request.GET.get('term')
    start_date  = request.GET.get('start_date')
    end_date    = request.GET.get('end_date')
    out_format  = (request.GET.get('export_format') or request.GET.get('format') or 'pdf').lower()

    if report_type != 'Fee Records':
        return HttpResponse("Only Fee Records supported.", status=400)

    def parse_date(s):
        try: return datetime.strptime(s, '%Y-%m-%d').date() if s else None
        except: return None

    start  = parse_date(start_date)
    end    = parse_date(end_date)
    search = request.GET.get('search', '').strip()
    mode   = request.GET.get('mode', 'all').lower()

    fees_qs = Fee.objects.filter(school_id=school_id).select_related('registration_no').order_by('-date_of_payment','-time')
    
    if mode != 'all':
        fees_qs = fees_qs.filter(mode_of_payment__iexact=mode)
    
    if search:
        fees_qs = fees_qs.filter(
            Q(registration_no__registration_no__icontains=search) |
            Q(registration_no__first_name__icontains=search) |
            Q(registration_no__surname__icontains=search)
        )

    if period == 'daily' and start:
        fees_qs = fees_qs.filter(date_of_payment=start)
        date_range_label, report_title = start.strftime('%d/%m/%Y'), f"Daily Fee Records ({start.strftime('%d/%m/%Y')})"
    elif period == 'weekly' and start and end:
        fees_qs = fees_qs.filter(date_of_payment__range=[start, end])
        date_range_label = f"{start.strftime('%d/%m/%Y')} – {end.strftime('%d/%m/%Y')}"
        report_title = "Weekly Fee Records"
    elif period == 'termly':
        if term:
            fees_qs = fees_qs.filter(term=term)
            date_range_label, report_title = term, f"Termly Fee Records ({term})"
        else:
            date_range_label, report_title = "All Terms", "Termly Fee Records"
    else:
        date_range_label, report_title = "All Time", "Fee Records"

    total_amount = fees_qs.aggregate(Sum('amount'))['amount__sum'] or 0

    if out_format in ['csv','excel']:
        sio = io.StringIO()
        w = csv.writer(sio)
        w.writerow(['Date','Reg No','Name','Grade','Term','Mode','Amount'])
        for fee in fees_qs:
            w.writerow([fee.date_of_payment, fee.registration_no.registration_no,
                        f"{fee.registration_no.first_name} {fee.registration_no.surname}",
                        fee.registration_no.grade, fee.term, fee.mode_of_payment, fee.amount])
        w.writerow([]); w.writerow(['Total','','','','','',total_amount])
        content      = sio.getvalue().encode('utf-8')
        content_type = 'text/csv' if out_format == 'csv' else 'application/vnd.ms-excel'
        filename     = f"fee_records_{period}_{datetime.now().date()}.{out_format}"
    else:
        pdf = FPDF()
        pdf.add_page()
        pdf_header(request, pdf, 30)
        draw_section_title(pdf, f"{report_title}  |  Period: {date_range_label}")

        cols = [('Date',25),('Reg No',25),('Name',50),('Mode',25),('Term',25),('Amount',30)]
        draw_styled_table_header(pdf, cols)
        for idx, fee in enumerate(fees_qs):
            draw_styled_row(pdf, [
                str(fee.date_of_payment), fee.registration_no.registration_no,
                f"{fee.registration_no.first_name} {fee.registration_no.surname}",
                fee.mode_of_payment, fee.term, f"{fee.amount:,}",
            ], [w for _,w in cols], idx, ['C','L','L','C','C','R'])

        pdf.ln(4)
        _set_fill(pdf, NAVY)
        _set_text(pdf, GOLD)
        pdf.set_font('Arial', 'B', 10)
        tw = sum(w for _,w in cols)
        pdf.rect(pdf.l_margin, pdf.get_y(), tw, 8, style='F')
        pdf.set_x(pdf.l_margin)
        pdf.cell(tw, 8, f"TOTAL COLLECTED:  Ksh {total_amount:,}", align='R')
        pdf.ln(10)
        _set_text(pdf, BLACK)
        pdf_footer(pdf)

        content      = pdf.output(dest='S').encode('latin1')
        content_type = 'application/pdf'
        filename     = f"fee_records_{period}_{datetime.now().date()}.pdf"

    resp = HttpResponse(content, content_type=content_type)
    resp['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# BULK LEAVE RECEIPTS
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def print_leave_receipts(request):
    school_id = request.user.school_id
    grade  = request.GET.get('grade')
    stream = request.GET.get('stream')
    term   = request.GET.get('term')

    student_qs = StudentInfo.objects.filter(school_id=school_id)
    if grade:  student_qs = student_qs.filter(grade=grade)
    if stream: student_qs = student_qs.filter(stream=stream)

    leaves_qs = LeaveManagement.objects.filter(
        school_id=school_id, status__iexact='approved',
        registration_no__in=student_qs.values_list('registration_no', flat=True)
    )
    if term: leaves_qs = leaves_qs.filter(term=term)
    all_leaves = leaves_qs.order_by('registration_no_id')

    pdf = PdfReciept()

    if not all_leaves.exists():
        pdf.add_page()
        pdf_header(request, pdf, 30)
        pdf.set_font('Arial', 'I', 11)
        pdf.cell(0, 10, f'No approved leave records found for Grade {grade} - Stream {stream}', align='C')
    else:
        for leave_data in all_leaves:
            student = leave_data.registration_no
            all_payments = Fee.objects.filter(school_id=school_id, registration_no=student.registration_no, term=leave_data.term)
            total_paid   = sum((p.amount or Decimal('0')) for p in all_payments)
            grade_obj    = Grade.objects.filter(school_id=school_id, name=student.grade).first()
            total_fees   = grade_obj.expected_fee if grade_obj and grade_obj.expected_fee else Decimal('0')
            balance      = total_fees - Decimal(total_paid)

            date = datetime.now()
            current_date = date.strftime("%d/%m/%Y")

            pdf.add_page()
            pdf.add_background_color()
            pdf.add_watermark(student.first_name.upper())
            pdf.set_text_color(0, 0, 0)
            pdf.add_header(request)

            _set_text(pdf, NAVY)
            pdf.set_font('Arial', 'BU', 10)
            pdf.cell(0, 6, 'LEAVE OUT RECEIPT', align='C', ln=True)
            pdf.ln(4)

            draw_section_title(pdf, "Student Details", w=pdf.w - pdf.l_margin - pdf.r_margin)
            pdf.info_pair("Reg No:", student.registration_no)
            pdf.info_pair("Name:",   f"{student.first_name} {student.second_name} {student.surname}")
            pdf.info_pair("Grade:",  student.grade)
            pdf.info_pair("Stream:", student.stream)
            pdf.info_pair("Term:",   leave_data.term)
            pdf.info_pair("Date:",   str(leave_data.date_of_leave or current_date))
            pdf.ln(3)

            _set_fill(pdf, SKY)
            pdf.rect(pdf.l_margin, pdf.get_y(), pdf.w - pdf.l_margin - pdf.r_margin, 10, style='F')
            _set_text(pdf, NAVY)
            pdf.set_font('Arial', 'I', 6)
            pdf.set_x(pdf.l_margin + 2)
            pdf.multi_cell(pdf.w - pdf.l_margin - pdf.r_margin - 4, 3,
                           "This is a confirmation receipt that the student named above has been granted permission to leave school premises.", align='C')
            pdf.ln(3)

            draw_section_title(pdf, "Leave Details", w=pdf.w - pdf.l_margin - pdf.r_margin)
            draw_styled_table_header(pdf, [('Reason For Leave', 45), ('Details', 45)])
            if leave_data.reason == 'School Fees':
                draw_styled_row(pdf, ['School Fees', f'Balance: {balance}'], [45,45], 0, ['L','L'])
            else:
                draw_styled_row(pdf, ['Other', str(leave_data.other_reason or '-')], [45,45], 0, ['L','L'])

            pdf.ln(8)
            _set_text(pdf, MID)
            pdf.set_font('Arial', '', 6)
            pdf.cell(0, 6, f'H/T SIGN & STAMP .......................   Date: {current_date}', ln=True)

            school = MasterSchool.objects.filter(id=school_id).first()
            pdf_footer(pdf, getattr(school, 'vision', '') if school else '')

    resp = HttpResponse(pdf.output(dest="S").encode('latin1'), content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="leave_receipts_{grade}_{stream}.pdf"'
    return resp






"""
report_views.py
===============
New analytical PDF report views derived from full model analysis.

MODELS INFERRED FROM pdf_views.py
===================================

1.  MasterSchool
        id, school_name, address, contact, email_address, motto, vision,
        logo_path (ImageField), status

2.  StudentInfo
        registration_no (PK / FK-like char),
        first_name, second_name, surname,
        grade, stream, school_id

3.  SubStrandMark
        student  → FK StudentInfo
        sub_strand → FK SubStrand
        level    (numeric 1-4 CBC scale)
        score    (numeric %)
        assessment_type  ('SBA-Project' | 'SBA-Practical' | 'SBA-Written')
        term, year
        school_id (via student relation)

4.  SubStrand
        strand  → FK Strand

5.  Strand
        subject  (Learning Area name, e.g. "Mathematics")
        grade    (e.g. "Grade 7")
        school_id

6.  LearnerCompetency
        student  → FK StudentInfo
        term, year
        competency   (name from core_competencies list)
        subject      (Learning Area name)
        level        (numeric)

7.  Fee
        registration_no → FK StudentInfo (char field used as FK)
        amount, term, date_of_payment, time
        mode_of_payment  ('M-Pesa' | 'Cash' | 'Bank Transfer')
        school_id

8.  GradeFeeConfig   (alias Grade in some places)
        grade / name   (grade label)
        expected_fee
        school_id

9.  Grade  (used interchangeably with GradeFeeConfig in some views)
        name, expected_fee, school_id

10. GradeStream
        grade, stream, school_id

11. LeaveManagement
        registration_no → FK StudentInfo
        reason, other_reason
        date_of_leave, return_date
        term, status ('Pending'|'Approved'|'Rejected')
        school_id

12. StudentAttendance
        registration_no (FK to StudentInfo)
        date_of_attendance
        term, school_id

NEW REPORTS ADDED
==================
1.  school_performance_summary      – whole-school CBC level breakdown across all grades/streams/terms
2.  class_grade_analysis_report     – per-grade, per-stream deep-dive with subject means, top students, CBC distribution
3.  subject_performance_report      – per-subject across the school or filtered by grade/term
4.  student_ranking_report          – ranked student list with overall level + score, filtered by grade/stream/term
5.  fee_collection_summary_report   – income summary: collected vs expected, defaulters list
6.  attendance_summary_report       – per-student and per-class attendance rate analysis
7.  leave_analysis_report           – leave reason breakdown, pending vs approved stats
8.  competency_heatmap_report       – school-wide competency strengths/gaps grid
"""

import io
import csv
from collections import defaultdict
from decimal import Decimal
from datetime import datetime

from django.http import HttpResponse
from django.contrib import messages
from django.db.models import Avg, Count, Sum, Q, Max, Min
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from fpdf import FPDF

from core.models import (
    MasterSchool, StudentInfo, SubStrandMark,
    Strand, LearnerCompetency,
    Fee, GradeFeeConfig, LeaveManagement,
    StudentAttendance,
)

from .pdf_styles import (
    PdfReportForm, PdfReciept,
    pdf_header, pdf_footer,
    draw_section_title, draw_styled_table_header, draw_styled_row,
    get_cbc_level_and_remark, core_competencies,
    CBC_LEVEL_MAP,
    NAVY, GOLD, SKY, WHITE, MID, GREEN, CRIMSON, GREY, BLACK,
    _set_fill, _set_text, _set_draw,
)

# ── Shared mini-helpers ────────────────────────────────────────────────────────

def _cbc_band(avg_level):
    """Return short band label given a numeric average level."""
    return get_cbc_level_and_remark(avg_level)['level']


def _progress_bar(pdf, x, y, w, h, pct, fill_rgb, bg_rgb=(220, 220, 220)):
    """Draw a simple horizontal progress bar."""
    _set_fill(pdf, bg_rgb)
    pdf.rect(x, y, w, h, style='F')
    bar_w = max(0, min(w * pct / 100, w))
    _set_fill(pdf, fill_rgb)
    pdf.rect(x, y, bar_w, h, style='F')
    _set_fill(pdf, WHITE)


def _mini_kpi(pdf, label, value, sub='', fill=NAVY, text_color=GOLD, w=44, h=18):
    """Draw a small KPI card block."""
    x0, y0 = pdf.get_x(), pdf.get_y()
    _set_fill(pdf, fill)
    _set_draw(pdf, fill)
    pdf.rect(x0, y0, w, h, style='F')
    _set_text(pdf, text_color)
    pdf.set_font('Arial', 'B', 14)
    pdf.set_xy(x0, y0 + 2)
    pdf.cell(w, 7, str(value), align='C')
    pdf.set_font('Arial', '', 6)
    _set_text(pdf, WHITE)
    pdf.set_xy(x0, y0 + 9)
    pdf.cell(w, 4, label, align='C')
    if sub:
        pdf.set_xy(x0, y0 + 13)
        pdf.cell(w, 4, sub, align='C')
    pdf.set_xy(x0 + w + 2, y0)
    _set_text(pdf, BLACK)
    _set_draw(pdf, BLACK)


def _gold_divider(pdf):
    """Thin gold horizontal rule."""
    _set_draw(pdf, GOLD)
    pdf.set_line_width(0.5)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.set_line_width(0.2)
    _set_draw(pdf, BLACK)
    pdf.ln(3)


# ─────────────────────────────────────────────────────────────────────────────
# 1.  SCHOOL PERFORMANCE SUMMARY
# GET /reports/school_performance_summary/?term=Term1&year=2024
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def school_performance_summary(request):
    """
    Whole-school summary:
      • KPI strip (total students, avg level, avg score, top grade)
      • Grade-by-grade performance table
      • CBC band distribution (EE / ME / AE / BE counts)
      • Top 10 students school-wide
    Filters: term, year
    """
    school_id = request.user.school_id
    messages.get_messages(request).used = True

    term = request.GET.get('term', '')
    year = request.GET.get('year', str(datetime.now().year))

    # ── 1. Aggregate per student ──────────────────────────────────────────────
    base_q = Q(student__school_id=school_id)
    if term: base_q &= Q(term=term)
    if year: base_q &= Q(year=year)

    student_avgs = (
        SubStrandMark.objects
        .filter(base_q)
        .values('student__registration_no', 'student__grade', 'student__stream',
                'student__first_name', 'student__surname')
        .annotate(avg_level=Avg('level'), avg_score=Avg('score'))
    )

    # ── 2. Grade rollup ──────────────────────────────────────────────────────
    grade_stats = defaultdict(lambda: {'levels': [], 'scores': [], 'count': 0})
    band_counts  = defaultdict(lambda: {'EE':0,'ME':0,'AE':0,'BE':0})
    top_students = []

    for s in student_avgs:
        g = s['student__grade']
        lv = s['avg_level'] or 0
        sc = s['avg_score'] or 0
        grade_stats[g]['levels'].append(lv)
        grade_stats[g]['scores'].append(sc)
        grade_stats[g]['count'] += 1
        band = _cbc_band(lv)
        if band in band_counts[g]:
            band_counts[g][band] += 1
        top_students.append({
            'reg':   s['student__registration_no'],
            'name':  f"{s['student__first_name']} {s['student__surname']}".strip(),
            'grade': g,
            'level': round(lv, 2),
            'score': round(sc, 1),
        })

    grade_rows = []
    for g, data in sorted(grade_stats.items()):
        levels = data['levels']
        scores = data['scores']
        avg_lv = round(sum(levels)/len(levels), 2) if levels else 0
        avg_sc = round(sum(scores)/len(scores), 1) if scores else 0
        grade_rows.append({
            'grade': g, 'count': data['count'],
            'avg_level': avg_lv, 'avg_score': avg_sc,
            'band': _cbc_band(avg_lv),
            'EE': band_counts[g]['EE'], 'ME': band_counts[g]['ME'],
            'AE': band_counts[g]['AE'], 'BE': band_counts[g]['BE'],
        })

    top10 = sorted(top_students, key=lambda x: x['level'], reverse=True)[:10]

    # ── KPI values ───────────────────────────────────────────────────────────
    all_levels = [s['avg_level'] for s in student_avgs if s['avg_level']]
    all_scores = [s['avg_score'] for s in student_avgs if s['avg_score']]
    school_avg_level = round(sum(all_levels)/len(all_levels), 2) if all_levels else 0
    school_avg_score = round(sum(all_scores)/len(all_scores), 1) if all_scores else 0
    total_students   = len(top_students)
    top_grade_row    = max(grade_rows, key=lambda r: r['avg_level'], default={'grade':'-'})

    # ── PDF ──────────────────────────────────────────────────────────────────
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf_header(request, pdf, 30)

    _set_text(pdf, NAVY)
    pdf.set_font('Arial', 'BU', 14)
    pdf.cell(0, 7, 'SCHOOL PERFORMANCE SUMMARY REPORT', align='C', ln=True)
    _set_text(pdf, MID)
    pdf.set_font('Arial', '', 9)
    pdf.cell(0, 5, f"Term: {term or 'All'}   |   Year: {year}   |   Generated: {datetime.now().strftime('%d/%m/%Y %H:%M')}",
             align='C', ln=True)
    pdf.ln(5)

    # ── KPI strip ────────────────────────────────────────────────────────────
    _set_text(pdf, BLACK)
    kpis = [
        ('Total Students',   total_students,  ''),
        ('School Avg Level', school_avg_level, f"({_cbc_band(school_avg_level)})"),
        ('School Avg Score', f"{school_avg_score}%", ''),
        ('Top Performing',   top_grade_row['grade'], ''),
    ]
    kpi_colors = [NAVY, (0,100,80), (120,60,0), (80,0,100)]
    pdf.set_x(pdf.l_margin)
    for (label, val, sub), col in zip(kpis, kpi_colors):
        _mini_kpi(pdf, label, val, sub, fill=col)
    pdf.ln(22)

    _gold_divider(pdf)

    # ── Grade performance table ───────────────────────────────────────────────
    draw_section_title(pdf, "Grade-by-Grade Performance")
    g_cols = [
        ('Grade',28),('Students',20),('Avg Level',22),('Avg Score',22),
        ('Band',14),('EE',14),('ME',14),('AE',14),('BE',14),
    ]
    draw_styled_table_header(pdf, g_cols)
    widths = [w for _, w in g_cols]

    for idx, row in enumerate(grade_rows):
        band_color = {'EE': GREEN, 'ME': NAVY, 'AE': (180,120,0), 'BE': CRIMSON}.get(row['band'], BLACK)
        fill = SKY if idx % 2 == 0 else WHITE
        _set_fill(pdf, fill)
        _set_draw(pdf, (210,220,230))
        pdf.set_font('Arial', 'B', 7)
        _set_text(pdf, NAVY)
        pdf.cell(widths[0], 6, row['grade'], border=1, align='L', fill=True)
        pdf.set_font('Arial', '', 6)
        _set_text(pdf, BLACK)
        pdf.cell(widths[1], 6, str(row['count']),     border=1, align='C', fill=True)
        pdf.cell(widths[2], 6, str(row['avg_level']), border=1, align='C', fill=True)
        pdf.cell(widths[3], 6, f"{row['avg_score']}%", border=1, align='C', fill=True)
        _set_text(pdf, band_color)
        pdf.set_font('Arial', 'B', 6)
        pdf.cell(widths[4], 6, row['band'], border=1, align='C', fill=True)
        _set_text(pdf, BLACK)
        pdf.set_font('Arial', '', 6)
        pdf.cell(widths[5], 6, str(row['EE']), border=1, align='C', fill=True)
        pdf.cell(widths[6], 6, str(row['ME']), border=1, align='C', fill=True)
        pdf.cell(widths[7], 6, str(row['AE']), border=1, align='C', fill=True)
        _set_text(pdf, CRIMSON)
        pdf.cell(widths[8], 6, str(row['BE']), border=1, align='C', fill=True)
        pdf.ln()
    _set_text(pdf, BLACK)

    # ── CBC Band distribution visual ─────────────────────────────────────────
    pdf.ln(5)
    draw_section_title(pdf, "CBC Band Distribution (School-wide)")
    total_any = sum(r['EE']+r['ME']+r['AE']+r['BE'] for r in grade_rows) or 1
    band_totals = {
        'EE': sum(r['EE'] for r in grade_rows),
        'ME': sum(r['ME'] for r in grade_rows),
        'AE': sum(r['AE'] for r in grade_rows),
        'BE': sum(r['BE'] for r in grade_rows),
    }
    band_colors_map = {'EE': GREEN, 'ME': NAVY, 'AE': (180,120,0), 'BE': CRIMSON}
    bar_w = pdf.w - pdf.l_margin - pdf.r_margin - 30
    for band, cnt in band_totals.items():
        pct = round(cnt / total_any * 100, 1)
        _set_text(pdf, band_colors_map[band])
        pdf.set_font('Arial', 'B', 7)
        pdf.set_x(pdf.l_margin)
        pdf.cell(18, 6, band)
        _progress_bar(pdf, pdf.get_x(), pdf.get_y() + 1, bar_w, 4, pct, band_colors_map[band])
        pdf.set_x(pdf.get_x() + bar_w + 2)
        _set_text(pdf, BLACK)
        pdf.set_font('Arial', '', 6)
        pdf.cell(20, 6, f"{cnt}  ({pct}%)", ln=True)
    _set_text(pdf, BLACK)

    # ── Top 10 students ──────────────────────────────────────────────────────
    pdf.ln(4)
    draw_section_title(pdf, "Top 10 Learners (School-wide)")
    t_cols = [('#',10),('Reg No',28),('Name',65),('Grade',22),('Avg Level',22),('Band',18)]
    draw_styled_table_header(pdf, t_cols)
    t_widths = [w for _, w in t_cols]
    for pos, s in enumerate(top10, 1):
        band = _cbc_band(s['level'])
        clr  = {'EE': GREEN, 'ME': NAVY, 'AE': (180,120,0), 'BE': CRIMSON}.get(band, BLACK)
        fill = SKY if pos % 2 == 0 else WHITE
        _set_fill(pdf, fill)
        _set_draw(pdf, (210,220,230))
        pdf.set_font('Arial', 'B', 7)
        _set_text(pdf, GOLD if pos <= 3 else BLACK)
        pdf.cell(t_widths[0], 6, str(pos), border=1, align='C', fill=True)
        _set_text(pdf, BLACK)
        pdf.set_font('Arial', '', 6)
        pdf.cell(t_widths[1], 6, s['reg'],   border=1, align='L', fill=True)
        pdf.cell(t_widths[2], 6, s['name'],  border=1, align='L', fill=True)
        pdf.cell(t_widths[3], 6, s['grade'], border=1, align='C', fill=True)
        pdf.cell(t_widths[4], 6, str(s['level']), border=1, align='C', fill=True)
        _set_text(pdf, clr)
        pdf.set_font('Arial', 'B', 6)
        pdf.cell(t_widths[5], 6, band, border=1, align='C', fill=True)
        pdf.ln()
    _set_text(pdf, BLACK)

    pdf_footer(pdf)
    resp = HttpResponse(pdf.output(dest='S').encode('latin1'), content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="school_performance_summary_{term}_{year}.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# 2.  CLASS / GRADE ANALYSIS REPORT
# GET /reports/class_grade_analysis/?grade=Grade7&stream=Mango&term=Term1&year=2024
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def class_grade_analysis_report(request):
    """
    Deep-dive per class (grade + stream + term):
      • Class KPI strip
      • Subject mean table with progress bars
      • Full ranked student list
      • CBC band pie-text summary
      • Top 5 / Bottom 5 students
    """
    school_id = request.user.school_id
    messages.get_messages(request).used = True

    grade  = request.GET.get('grade', '')
    stream = request.GET.get('stream', '')
    term   = request.GET.get('term', '')
    year   = request.GET.get('year', str(datetime.now().year))

    if not grade:
        return HttpResponse("grade parameter is required.", status=400)

    base_q = Q(student__school_id=school_id, sub_strand__strand__grade=grade)
    if stream: base_q &= Q(student__stream=stream)
    if term:   base_q &= Q(term=term)
    if year:   base_q &= Q(year=year)

    # ── Subject means ─────────────────────────────────────────────────────────
    subject_avgs = (
        SubStrandMark.objects.filter(base_q)
        .values('sub_strand__strand__subject')
        .annotate(avg_level=Avg('level'), avg_score=Avg('score'), count=Count('id'))
        .order_by('-avg_level')
    )

    # ── Per-student means ─────────────────────────────────────────────────────
    student_avgs = (
        SubStrandMark.objects.filter(base_q)
        .values('student__registration_no', 'student__first_name',
                'student__second_name', 'student__surname', 'student__stream')
        .annotate(avg_level=Avg('level'), avg_score=Avg('score'))
    )

    # Rank
    ranked = sorted(student_avgs, key=lambda x: x['avg_level'] or 0, reverse=True)
    for pos, s in enumerate(ranked, 1):
        s['rank'] = pos

    # Band counts
    bands = {'EE':0,'ME':0,'AE':0,'BE':0}
    for s in ranked:
        b = _cbc_band(s['avg_level'] or 0)
        if b in bands: bands[b] += 1

    total_students   = len(ranked)
    all_lv  = [s['avg_level'] for s in ranked if s['avg_level']]
    all_sc  = [s['avg_score'] for s in ranked if s['avg_score']]
    class_avg_level  = round(sum(all_lv)/len(all_lv), 2) if all_lv else 0
    class_avg_score  = round(sum(all_sc)/len(all_sc), 1) if all_sc else 0
    top5    = ranked[:5]
    bottom5 = ranked[-5:][::-1]

    # ── PDF ──────────────────────────────────────────────────────────────────
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf_header(request, pdf, 30)

    _set_text(pdf, NAVY)
    pdf.set_font('Arial', 'BU', 13)
    pdf.cell(0, 7, 'CLASS / GRADE ANALYSIS REPORT', align='C', ln=True)
    _set_text(pdf, MID)
    pdf.set_font('Arial', '', 9)
    label_parts = [f"Grade: {grade}"]
    if stream: label_parts.append(f"Stream: {stream}")
    if term:   label_parts.append(f"Term: {term}")
    label_parts.append(f"Year: {year}")
    pdf.cell(0, 5, '   |   '.join(label_parts), align='C', ln=True)
    pdf.ln(5)

    # ── KPI strip ────────────────────────────────────────────────────────────
    kpis = [
        ('Total Learners',    total_students,       ''),
        ('Class Avg Level',   class_avg_level,      f"({_cbc_band(class_avg_level)})"),
        ('Class Avg Score',   f"{class_avg_score}%",''),
        ('Exceeding Expect.', bands['EE'],           'EE learners'),
        ('Need Intervention', bands['BE'],           'BE learners'),
    ]
    kpi_colors = [NAVY, (0,100,80), (120,60,0), GREEN, CRIMSON]
    for (label, val, sub), col in zip(kpis, kpi_colors):
        _mini_kpi(pdf, label, val, sub, fill=col, w=36)
    pdf.ln(22)
    _gold_divider(pdf)

    # ── Subject means ─────────────────────────────────────────────────────────
    draw_section_title(pdf, "Subject Performance Overview")
    s_cols = [('Learning Area',55),('Avg Level',25),('Band',18),('Avg Score',25),('Progress',55)]
    draw_styled_table_header(pdf, s_cols)
    s_widths = [w for _, w in s_cols]

    max_score = max((r['avg_score'] or 0 for r in subject_avgs), default=100) or 100

    for idx, row in enumerate(subject_avgs):
        lv   = row['avg_level'] or 0
        sc   = row['avg_score'] or 0
        band = _cbc_band(lv)
        bclr = {'EE':GREEN,'ME':NAVY,'AE':(180,120,0),'BE':CRIMSON}.get(band, BLACK)
        fill = SKY if idx % 2 == 0 else WHITE
        _set_fill(pdf, fill)
        _set_draw(pdf, (210,220,230))
        pdf.set_font('Arial', '', 7)
        _set_text(pdf, BLACK)
        pdf.cell(s_widths[0], 7, str(row['sub_strand__strand__subject'] or '-'), border=1, align='L', fill=True)
        pdf.cell(s_widths[1], 7, str(round(lv,2)),  border=1, align='C', fill=True)
        _set_text(pdf, bclr)
        pdf.set_font('Arial', 'B', 7)
        pdf.cell(s_widths[2], 7, band, border=1, align='C', fill=True)
        _set_text(pdf, BLACK)
        pdf.set_font('Arial', '', 7)
        pdf.cell(s_widths[3], 7, f"{round(sc,1)}%", border=1, align='C', fill=True)

        # inline mini bar
        bx = pdf.get_x() + 1
        by = pdf.get_y() + 2
        _progress_bar(pdf, bx, by, s_widths[4]-2, 3, sc / max_score * 100, bclr)
        pdf.cell(s_widths[4], 7, '', border=1, fill=False)
        pdf.ln()
    _set_text(pdf, BLACK)

    # ── CBC band summary ──────────────────────────────────────────────────────
    pdf.ln(4)
    draw_section_title(pdf, "CBC Band Distribution")
    band_colors_map = {'EE':GREEN,'ME':NAVY,'AE':(180,120,0),'BE':CRIMSON}
    bar_w = 120
    tot = total_students or 1
    for band, cnt in bands.items():
        pct = round(cnt / tot * 100, 1)
        _set_text(pdf, band_colors_map[band])
        pdf.set_font('Arial', 'B', 7)
        pdf.set_x(pdf.l_margin)
        lbl = {'EE':'Exceeding Expectations','ME':'Meeting Expectations',
               'AE':'Approaching Expectations','BE':'Below Expectations'}[band]
        pdf.cell(55, 6, f"{band} – {lbl}")
        _progress_bar(pdf, pdf.get_x(), pdf.get_y()+1, bar_w, 4, pct, band_colors_map[band])
        pdf.set_x(pdf.get_x() + bar_w + 2)
        _set_text(pdf, BLACK)
        pdf.set_font('Arial', '', 6)
        pdf.cell(25, 6, f"{cnt} ({pct}%)", ln=True)
    _set_text(pdf, BLACK)

    # ── Top 5 / Bottom 5 ─────────────────────────────────────────────────────
    pdf.ln(4)
    for section_label, student_list, hdr_color in [
        ('Top 5 Learners', top5, GREEN),
        ('Learners Needing Support (Bottom 5)', bottom5, CRIMSON),
    ]:
        draw_section_title(pdf, section_label)
        tb_cols = [('#',10),('Reg No',30),('Name',65),('Stream',22),('Avg Level',22),('Band',18)]
        draw_styled_table_header(pdf, tb_cols)
        tb_w = [w for _, w in tb_cols]
        for i, s in enumerate(student_list):
            band = _cbc_band(s['avg_level'] or 0)
            bclr = {'EE':GREEN,'ME':NAVY,'AE':(180,120,0),'BE':CRIMSON}.get(band, BLACK)
            name = f"{s['student__first_name']} {s['student__second_name'] or ''} {s['student__surname']}".strip()
            fill = SKY if i % 2 == 0 else WHITE
            _set_fill(pdf, fill)
            _set_draw(pdf, (210,220,230))
            pdf.set_font('Arial', 'B', 7)
            _set_text(pdf, hdr_color)
            pdf.cell(tb_w[0], 6, str(s['rank']), border=1, align='C', fill=True)
            _set_text(pdf, BLACK)
            pdf.set_font('Arial', '', 6)
            pdf.cell(tb_w[1], 6, s['student__registration_no'], border=1, align='L', fill=True)
            pdf.cell(tb_w[2], 6, name,                          border=1, align='L', fill=True)
            pdf.cell(tb_w[3], 6, s['student__stream'] or '-',   border=1, align='C', fill=True)
            pdf.cell(tb_w[4], 6, str(round(s['avg_level'] or 0,2)), border=1, align='C', fill=True)
            _set_text(pdf, bclr)
            pdf.set_font('Arial', 'B', 6)
            pdf.cell(tb_w[5], 6, band, border=1, align='C', fill=True)
            pdf.ln()
        _set_text(pdf, BLACK)
        pdf.ln(4)

    # ── Full ranked student list ──────────────────────────────────────────────
    draw_section_title(pdf, "Full Ranked Student List")
    fr_cols = [('Rank',12),('Reg No',28),('Name',55),('Stream',18),
               ('Avg Lv',18),('Avg Sc',18),('Band',14)]
    draw_styled_table_header(pdf, fr_cols)
    fr_w = [w for _, w in fr_cols]
    for s in ranked:
        band = _cbc_band(s['avg_level'] or 0)
        bclr = {'EE':GREEN,'ME':NAVY,'AE':(180,120,0),'BE':CRIMSON}.get(band, BLACK)
        name = f"{s['student__first_name']} {s['student__second_name'] or ''} {s['student__surname']}".strip()
        fill = SKY if s['rank'] % 2 == 0 else WHITE
        _set_fill(pdf, fill)
        _set_draw(pdf, (210,220,230))
        pdf.set_font('Arial', '', 6)
        _set_text(pdf, BLACK)
        pdf.cell(fr_w[0], 5, str(s['rank']),                        border=1, align='C', fill=True)
        pdf.cell(fr_w[1], 5, s['student__registration_no'],          border=1, align='L', fill=True)
        pdf.cell(fr_w[2], 5, name[:30],                              border=1, align='L', fill=True)
        pdf.cell(fr_w[3], 5, s['student__stream'] or '-',            border=1, align='C', fill=True)
        pdf.cell(fr_w[4], 5, str(round(s['avg_level'] or 0,2)),      border=1, align='C', fill=True)
        pdf.cell(fr_w[5], 5, f"{round(s['avg_score'] or 0,1)}%",     border=1, align='C', fill=True)
        _set_text(pdf, bclr)
        pdf.set_font('Arial', 'B', 6)
        pdf.cell(fr_w[6], 5, band, border=1, align='C', fill=True)
        pdf.ln()
    _set_text(pdf, BLACK)

    pdf_footer(pdf)
    safe = lambda s: s.replace(' ', '_') if s else 'all'
    resp = HttpResponse(pdf.output(dest='S').encode('latin1'), content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="class_analysis_{safe(grade)}_{safe(stream)}_{safe(term)}.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# 3.  SUBJECT PERFORMANCE REPORT
# GET /reports/subject_performance/?grade=Grade7&term=Term1&year=2024
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def subject_performance_report(request):
    """
    For each Learning Area (subject) in a grade:
      • Mean level + mean score
      • Per assessment-type breakdown (Project / Practical / Written)
      • Top 5 students per subject
    Filters: grade, stream, term, year
    """
    school_id = request.user.school_id
    messages.get_messages(request).used = True

    grade  = request.GET.get('grade', '')
    stream = request.GET.get('stream', '')
    term   = request.GET.get('term', '')
    year   = request.GET.get('year', str(datetime.now().year))

    base_q = Q(student__school_id=school_id)
    if grade:  base_q &= Q(sub_strand__strand__grade=grade)
    if stream: base_q &= Q(student__stream=stream)
    if term:   base_q &= Q(term=term)
    if year:   base_q &= Q(year=year)

    # Subject × assessment_type breakdown
    raw = (
        SubStrandMark.objects.filter(base_q)
        .values('sub_strand__strand__subject', 'assessment_type')
        .annotate(avg_level=Avg('level'), avg_score=Avg('score'), n=Count('id'))
    )

    # Restructure: {subject: {assessment_type: {level,score,n}}}
    subj_data = defaultdict(lambda: defaultdict(lambda: {'level':0,'score':0,'n':0}))
    subjects  = set()
    for r in raw:
        subj = r['sub_strand__strand__subject']
        at   = r['assessment_type'] or 'General'
        subjects.add(subj)
        subj_data[subj][at]['level'] = round(r['avg_level'] or 0, 2)
        subj_data[subj][at]['score'] = round(r['avg_score'] or 0, 1)
        subj_data[subj][at]['n']     = r['n']

    # Overall per subject
    subj_overall = {}
    for subj in subjects:
        overall_qs = (
            SubStrandMark.objects.filter(base_q, sub_strand__strand__subject=subj)
            .aggregate(avg_level=Avg('level'), avg_score=Avg('score'), n=Count('id'))
        )
        subj_overall[subj] = {
            'level': round(overall_qs['avg_level'] or 0, 2),
            'score': round(overall_qs['avg_score'] or 0, 1),
            'n':     overall_qs['n'],
        }

    # Top 5 per subject
    subj_top5 = {}
    for subj in subjects:
        top_qs = (
            SubStrandMark.objects.filter(base_q, sub_strand__strand__subject=subj)
            .values('student__registration_no','student__first_name','student__surname')
            .annotate(avg_level=Avg('level'), avg_score=Avg('score'))
            .order_by('-avg_level')[:5]
        )
        subj_top5[subj] = list(top_qs)

    # ── PDF ──────────────────────────────────────────────────────────────────
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf_header(request, pdf, 30)

    _set_text(pdf, NAVY)
    pdf.set_font('Arial', 'BU', 13)
    pdf.cell(0, 7, 'SUBJECT PERFORMANCE REPORT', align='C', ln=True)
    _set_text(pdf, MID)
    pdf.set_font('Arial', '', 9)
    parts = []
    if grade:  parts.append(f"Grade: {grade}")
    if stream: parts.append(f"Stream: {stream}")
    if term:   parts.append(f"Term: {term}")
    parts.append(f"Year: {year}")
    pdf.cell(0, 5, '   |   '.join(parts), align='C', ln=True)
    pdf.ln(6)

    assessment_types = ['SBA-Project','SBA-Practical','SBA-Written','General']

    for subj in sorted(subjects):
        draw_section_title(pdf, subj)
        overall = subj_overall.get(subj, {})
        ol  = overall.get('level', 0)
        os_ = overall.get('score', 0)
        band = _cbc_band(ol)
        bclr = {'EE':GREEN,'ME':NAVY,'AE':(180,120,0),'BE':CRIMSON}.get(band, BLACK)

        # Overall summary row
        _set_fill(pdf, NAVY)
        _set_text(pdf, GOLD)
        pdf.set_font('Arial', 'B', 8)
        pdf.cell(60, 7, f"Overall Avg Level: {ol}  ({band})", fill=True, align='L')
        pdf.cell(50, 7, f"Overall Avg Score: {os_}%", fill=True, align='L')
        pdf.cell(30, 7, f"Total Records: {overall.get('n',0)}", fill=True, align='L')
        pdf.ln(7)
        _set_text(pdf, BLACK)

        # Assessment-type breakdown table
        at_cols = [('Assessment Type',50),('Avg Level',30),('Band',20),('Avg Score',30),('Records',25)]
        draw_styled_table_header(pdf, at_cols)
        at_widths = [w for _, w in at_cols]
        for idx, at in enumerate(assessment_types):
            data = subj_data[subj].get(at, {})
            if not data.get('n'): continue
            lv   = data['level']
            sc   = data['score']
            b    = _cbc_band(lv)
            bc   = {'EE':GREEN,'ME':NAVY,'AE':(180,120,0),'BE':CRIMSON}.get(b, BLACK)
            fill = SKY if idx % 2 == 0 else WHITE
            _set_fill(pdf, fill)
            _set_draw(pdf, (210,220,230))
            pdf.set_font('Arial', '', 7)
            _set_text(pdf, BLACK)
            pdf.cell(at_widths[0], 6, at,       border=1, align='L', fill=True)
            pdf.cell(at_widths[1], 6, str(lv),  border=1, align='C', fill=True)
            _set_text(pdf, bc)
            pdf.set_font('Arial', 'B', 7)
            pdf.cell(at_widths[2], 6, b,         border=1, align='C', fill=True)
            _set_text(pdf, BLACK)
            pdf.set_font('Arial', '', 7)
            pdf.cell(at_widths[3], 6, f"{sc}%",  border=1, align='C', fill=True)
            pdf.cell(at_widths[4], 6, str(data['n']), border=1, align='C', fill=True)
            pdf.ln()
        _set_text(pdf, BLACK)

        # Top 5 for this subject
        top5 = subj_top5.get(subj, [])
        if top5:
            pdf.ln(2)
            _set_text(pdf, MID)
            pdf.set_font('Arial', 'BI', 7)
            pdf.cell(0, 4, f"  Top 5 in {subj}:", ln=True)
            tp_cols = [('#',10),('Reg No',28),('Name',65),('Avg Level',25),('Band',18)]
            draw_styled_table_header(pdf, tp_cols)
            tp_w = [w for _, w in tp_cols]
            for pos, s in enumerate(top5, 1):
                b    = _cbc_band(s['avg_level'] or 0)
                bc   = {'EE':GREEN,'ME':NAVY,'AE':(180,120,0),'BE':CRIMSON}.get(b, BLACK)
                name = f"{s['student__first_name']} {s['student__surname']}".strip()
                fill = SKY if pos % 2 == 0 else WHITE
                _set_fill(pdf, fill)
                _set_draw(pdf, (210,220,230))
                pdf.set_font('Arial', '', 6)
                _set_text(pdf, BLACK)
                pdf.cell(tp_w[0], 5, str(pos), border=1, align='C', fill=True)
                pdf.cell(tp_w[1], 5, s['student__registration_no'], border=1, align='L', fill=True)
                pdf.cell(tp_w[2], 5, name,   border=1, align='L', fill=True)
                pdf.cell(tp_w[3], 5, str(round(s['avg_level'] or 0,2)), border=1, align='C', fill=True)
                _set_text(pdf, bc)
                pdf.set_font('Arial', 'B', 6)
                pdf.cell(tp_w[4], 5, b, border=1, align='C', fill=True)
                pdf.ln()
        _set_text(pdf, BLACK)
        pdf.ln(5)

    pdf_footer(pdf)
    safe = lambda s: s.replace(' ','_') if s else 'all'
    resp = HttpResponse(pdf.output(dest='S').encode('latin1'), content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="subject_performance_{safe(grade)}_{safe(term)}.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# 4.  STUDENT RANKING REPORT
# GET /reports/student_ranking/?grade=Grade7&stream=Mango&term=Term1&year=2024
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def student_ranking_report(request):
    """
    Full ranked student list with:
      • Rank, name, grade, stream
      • Per-subject level in columns
      • Overall avg level + band
    Filters: grade, stream, term, year
    """
    school_id = request.user.school_id
    messages.get_messages(request).used = True

    grade  = request.GET.get('grade', '')
    stream = request.GET.get('stream', '')
    term   = request.GET.get('term', '')
    year   = request.GET.get('year', str(datetime.now().year))

    base_q = Q(student__school_id=school_id)
    if grade:  base_q &= Q(sub_strand__strand__grade=grade)
    if stream: base_q &= Q(student__stream=stream)
    if term:   base_q &= Q(term=term)
    if year:   base_q &= Q(year=year)

    # Per student × subject
    raw = (
        SubStrandMark.objects.filter(base_q)
        .values('student__registration_no','student__first_name',
                'student__second_name','student__surname','student__grade',
                'student__stream','sub_strand__strand__subject')
        .annotate(avg_level=Avg('level'), avg_score=Avg('score'))
    )

    student_subj = defaultdict(dict)
    student_info = {}
    subjects = set()
    for r in raw:
        rn   = r['student__registration_no']
        subj = r['sub_strand__strand__subject']
        subjects.add(subj)
        student_subj[rn][subj] = round(r['avg_level'] or 0, 2)
        if rn not in student_info:
            student_info[rn] = {
                'name':   f"{r['student__first_name']} {r['student__second_name'] or ''} {r['student__surname']}".strip(),
                'grade':  r['student__grade'],
                'stream': r['student__stream'],
            }

    # Overall avg level per student
    for rn in student_subj:
        vals = [v for v in student_subj[rn].values() if v]
        student_info[rn]['overall'] = round(sum(vals)/len(vals), 2) if vals else 0

    ranked = sorted(student_info.items(), key=lambda x: x[1]['overall'], reverse=True)
    subjects_list = sorted(subjects)

    # ── PDF (Landscape for wide table) ───────────────────────────────────────
    pdf = FPDF(orientation='L')
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf_header(request, pdf, 30)

    _set_text(pdf, NAVY)
    pdf.set_font('Arial', 'BU', 13)
    pdf.cell(0, 7, 'STUDENT RANKING REPORT', align='C', ln=True)
    _set_text(pdf, MID)
    pdf.set_font('Arial', '', 9)
    parts = []
    if grade:  parts.append(f"Grade: {grade}")
    if stream: parts.append(f"Stream: {stream}")
    if term:   parts.append(f"Term: {term}")
    parts.append(f"Year: {year}")
    pdf.cell(0, 5, '   |   '.join(parts), align='C', ln=True)
    pdf.ln(5)

    # Dynamic column widths
    fixed_w   = [12, 22, 50, 16, 16]  # Rank, Reg, Name, Grade, Stream
    avail_w   = pdf.w - pdf.l_margin - pdf.r_margin - sum(fixed_w) - 20 - 14
    subj_w    = round(avail_w / max(len(subjects_list), 1), 1)
    header    = [('Rank',12),('Reg No',22),('Name',50),('Grade',16),('Stream',16)]
    for s in subjects_list:
        abbr = s[:10]
        header.append((abbr, subj_w))
    header.append(('Ovr Lv', 20))
    header.append(('Band', 14))

    draw_styled_table_header(pdf, header)
    widths = [w for _, w in header]

    rank = 1
    prev_overall = None
    for rn, info in ranked:
        if prev_overall is not None and info['overall'] != prev_overall:
            rank += 1
        prev_overall = info['overall']

        band = _cbc_band(info['overall'])
        bclr = {'EE':GREEN,'ME':NAVY,'AE':(180,120,0),'BE':CRIMSON}.get(band, BLACK)
        fill = SKY if rank % 2 == 0 else WHITE
        _set_fill(pdf, fill)
        _set_draw(pdf, (210,220,230))
        pdf.set_font('Arial', 'B', 6)
        _set_text(pdf, GOLD if rank <= 3 else BLACK)
        pdf.cell(widths[0], 5, str(rank), border=1, align='C', fill=True)
        _set_text(pdf, BLACK)
        pdf.set_font('Arial', '', 5)
        pdf.cell(widths[1], 5, rn,               border=1, align='L', fill=True)
        pdf.cell(widths[2], 5, info['name'][:22], border=1, align='L', fill=True)
        pdf.cell(widths[3], 5, info['grade'],     border=1, align='C', fill=True)
        pdf.cell(widths[4], 5, info['stream'] or '-', border=1, align='C', fill=True)
        for i, subj in enumerate(subjects_list):
            lv = student_subj[rn].get(subj, '-')
            pdf.cell(widths[5+i], 5, str(lv), border=1, align='C', fill=True)
        pdf.cell(widths[-2], 5, str(info['overall']), border=1, align='C', fill=True)
        _set_text(pdf, bclr)
        pdf.set_font('Arial', 'B', 5)
        pdf.cell(widths[-1], 5, band, border=1, align='C', fill=True)
        pdf.ln()
    _set_text(pdf, BLACK)

    pdf_footer(pdf)
    safe = lambda s: s.replace(' ','_') if s else 'all'
    resp = HttpResponse(pdf.output(dest='S').encode('latin1'), content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="student_ranking_{safe(grade)}_{safe(stream)}_{safe(term)}.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# 5.  FEE COLLECTION SUMMARY REPORT
# GET /reports/fee_collection_summary/?grade=Grade7&stream=Mango&term=Term1
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def fee_collection_summary_report(request):
    """
    Financial summary per class:
      • Expected total vs collected total
      • Collection rate %
      • Per-student fee status (paid / partial / defaulter)
      • Defaulters list
    Filters: grade, stream, term
    """
    school_id = request.user.school_id
    messages.get_messages(request).used = True

    grade  = request.GET.get('grade', '')
    stream = request.GET.get('stream', '')
    term   = request.GET.get('term', '')

    students_qs = StudentInfo.objects.filter(school_id=school_id)
    if grade:  students_qs = students_qs.filter(grade=grade)
    if stream: students_qs = students_qs.filter(stream=stream)
    students = list(students_qs.order_by('registration_no'))

    fee_qs = Fee.objects.filter(school_id=school_id)
    if term:  fee_qs = fee_qs.filter(term=term)
    if grade: fee_qs = fee_qs.filter(registration_no__grade=grade)
    if stream:fee_qs = fee_qs.filter(registration_no__stream=stream)

    # Payment map
    pay_map = defaultdict(Decimal)
    for f in fee_qs:
        pay_map[f.registration_no_id] += Decimal(f.amount or 0)

    # Expected fee config
    grade_fee_cfg = GradeFeeConfig.objects.filter(school_id=school_id).first()
    expected_per_student = Decimal(grade_fee_cfg.expected_fee if grade_fee_cfg else 0)

    # Build rows
    rows = []
    for s in students:
        paid    = pay_map.get(s.registration_no, Decimal('0'))
        balance = expected_per_student - paid
        status  = 'Cleared' if balance <= 0 else ('Partial' if paid > 0 else 'Defaulter')
        rows.append({
            'reg':    s.registration_no,
            'name':   f"{s.first_name} {s.surname}".strip(),
            'grade':  s.grade,
            'stream': s.stream,
            'paid':   paid,
            'balance':balance,
            'status': status,
        })

    total_expected  = expected_per_student * len(students)
    total_collected = sum(r['paid'] for r in rows)
    total_balance   = total_expected - total_collected
    collection_rate = round(float(total_collected) / float(total_expected) * 100, 1) if total_expected else 0
    cleared   = sum(1 for r in rows if r['status'] == 'Cleared')
    partial   = sum(1 for r in rows if r['status'] == 'Partial')
    defaulters = [r for r in rows if r['status'] == 'Defaulter']

    # ── PDF ──────────────────────────────────────────────────────────────────
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf_header(request, pdf, 30)

    _set_text(pdf, NAVY)
    pdf.set_font('Arial', 'BU', 13)
    pdf.cell(0, 7, 'FEE COLLECTION SUMMARY REPORT', align='C', ln=True)
    _set_text(pdf, MID)
    pdf.set_font('Arial', '', 9)
    parts = []
    if grade:  parts.append(f"Grade: {grade}")
    if stream: parts.append(f"Stream: {stream}")
    if term:   parts.append(f"Term: {term}")
    pdf.cell(0, 5, '   |   '.join(parts) or 'All Classes', align='C', ln=True)
    pdf.ln(5)

    # ── KPI strip ────────────────────────────────────────────────────────────
    kpis = [
        ('Expected (Ksh)',  f"{total_expected:,.0f}", ''),
        ('Collected (Ksh)', f"{total_collected:,.0f}", ''),
        ('Balance (Ksh)',   f"{total_balance:,.0f}",  ''),
        ('Collection Rate', f"{collection_rate}%",    ''),
        ('Cleared',         cleared,                  'students'),
        ('Defaulters',      len(defaulters),           'students'),
    ]
    kpi_colors = [NAVY, GREEN, CRIMSON, (0,80,160), GREEN, CRIMSON]
    for (label, val, sub), col in zip(kpis, kpi_colors):
        _mini_kpi(pdf, label, val, sub, fill=col, w=31)
    pdf.ln(22)
    _gold_divider(pdf)

    # ── Collection rate bar ───────────────────────────────────────────────────
    draw_section_title(pdf, "Collection Rate")
    bar_w = pdf.w - pdf.l_margin - pdf.r_margin
    _progress_bar(pdf, pdf.l_margin, pdf.get_y(), bar_w, 6,
                  collection_rate, GREEN if collection_rate >= 80 else (180,120,0) if collection_rate >= 50 else CRIMSON)
    _set_text(pdf, WHITE)
    pdf.set_font('Arial', 'B', 7)
    pdf.set_xy(pdf.l_margin + bar_w/2 - 15, pdf.get_y())
    pdf.cell(30, 6, f"{collection_rate}% Collected")
    pdf.ln(8)
    _set_text(pdf, BLACK)

    # ── Full student fee status table ─────────────────────────────────────────
    draw_section_title(pdf, "Student Fee Status")
    f_cols = [('Reg No',28),('Name',60),('Grade',18),('Stream',18),
              ('Paid (Ksh)',28),('Balance (Ksh)',28),('Status',20)]
    draw_styled_table_header(pdf, f_cols)
    f_widths = [w for _, w in f_cols]
    for idx, r in enumerate(rows):
        sclr = {'Cleared':GREEN,'Partial':(180,120,0),'Defaulter':CRIMSON}.get(r['status'], BLACK)
        fill = SKY if idx % 2 == 0 else WHITE
        _set_fill(pdf, fill)
        _set_draw(pdf, (210,220,230))
        pdf.set_font('Arial', '', 7)
        _set_text(pdf, BLACK)
        pdf.cell(f_widths[0], 6, r['reg'],   border=1, align='L', fill=True)
        pdf.cell(f_widths[1], 6, r['name'],  border=1, align='L', fill=True)
        pdf.cell(f_widths[2], 6, r['grade'], border=1, align='C', fill=True)
        pdf.cell(f_widths[3], 6, r['stream'] or '-', border=1, align='C', fill=True)
        _set_text(pdf, GREEN)
        pdf.cell(f_widths[4], 6, f"{r['paid']:,.0f}", border=1, align='R', fill=True)
        _set_text(pdf, CRIMSON if r['balance'] > 0 else GREEN)
        pdf.cell(f_widths[5], 6, f"{r['balance']:,.0f}", border=1, align='R', fill=True)
        _set_text(pdf, sclr)
        pdf.set_font('Arial', 'B', 7)
        pdf.cell(f_widths[6], 6, r['status'], border=1, align='C', fill=True)
        pdf.ln()
    _set_text(pdf, BLACK)

    # ── Defaulters list ───────────────────────────────────────────────────────
    if defaulters:
        pdf.ln(5)
        draw_section_title(pdf, f"Defaulters List ({len(defaulters)} students)")
        d_cols = [('Reg No',28),('Name',80),('Grade',20),('Stream',20),('Balance (Ksh)',32)]
        draw_styled_table_header(pdf, d_cols)
        d_widths = [w for _, w in d_cols]
        for idx, r in enumerate(defaulters):
            fill = (255,240,240) if idx % 2 == 0 else WHITE
            _set_fill(pdf, fill)
            _set_draw(pdf, (210,220,230))
            pdf.set_font('Arial', '', 7)
            _set_text(pdf, BLACK)
            pdf.cell(d_widths[0], 6, r['reg'],  border=1, align='L', fill=True)
            pdf.cell(d_widths[1], 6, r['name'], border=1, align='L', fill=True)
            pdf.cell(d_widths[2], 6, r['grade'],border=1, align='C', fill=True)
            pdf.cell(d_widths[3], 6, r['stream'] or '-', border=1, align='C', fill=True)
            _set_text(pdf, CRIMSON)
            pdf.set_font('Arial', 'B', 7)
            pdf.cell(d_widths[4], 6, f"{r['balance']:,.0f}", border=1, align='R', fill=True)
            pdf.ln()
        _set_text(pdf, BLACK)

    pdf_footer(pdf)
    safe = lambda s: s.replace(' ','_') if s else 'all'
    resp = HttpResponse(pdf.output(dest='S').encode('latin1'), content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="fee_summary_{safe(grade)}_{safe(stream)}_{safe(term)}.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# 6.  ATTENDANCE SUMMARY REPORT
# GET /reports/attendance_summary/?grade=Grade7&stream=Mango&term=Term1
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def attendance_summary_report(request):
    """
    Attendance analysis:
      • Total school days on record
      • Per-student attendance count + rate %
      • Students with < 80 % attendance flagged
    Filters: grade, stream, term
    """
    school_id = request.user.school_id
    messages.get_messages(request).used = True

    grade  = request.GET.get('grade', '')
    stream = request.GET.get('stream', '')
    term   = request.GET.get('term', '')

    students_qs = StudentInfo.objects.filter(school_id=school_id)
    if grade:  students_qs = students_qs.filter(grade=grade)
    if stream: students_qs = students_qs.filter(stream=stream)
    students = list(students_qs.order_by('registration_no'))

    att_qs = StudentAttendance.objects.filter(school_id=school_id)
    if grade:  att_qs = att_qs.filter(registration_no__grade=grade)
    if stream: att_qs = att_qs.filter(registration_no__stream=stream)
    if term:   att_qs = att_qs.filter(term=term)

    # Total distinct school days
    unique_dates = att_qs.values_list('date_of_attendance', flat=True).distinct()
    total_days = len(set(unique_dates)) or 1

    # Per-student attendance count
    att_counts = defaultdict(int)
    att_dates  = defaultdict(list)
    for a in att_qs:
        att_counts[a.registration_no_id] += 1
        att_dates[a.registration_no_id].append(a.date_of_attendance)

    # Build rows
    rows = []
    for s in students:
        cnt  = att_counts.get(s.registration_no, 0)
        rate = round(cnt / total_days * 100, 1)
        rows.append({
            'reg':    s.registration_no,
            'name':   f"{s.first_name} {s.surname}".strip(),
            'grade':  s.grade,
            'stream': s.stream,
            'days_present': cnt,
            'total_days':   total_days,
            'rate':   rate,
            'flag':   rate < 80,
        })

    rows_sorted = sorted(rows, key=lambda r: r['rate'])
    poor_attendance = [r for r in rows if r['flag']]
    avg_rate = round(sum(r['rate'] for r in rows)/len(rows), 1) if rows else 0

    # ── PDF ──────────────────────────────────────────────────────────────────
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf_header(request, pdf, 30)

    _set_text(pdf, NAVY)
    pdf.set_font('Arial', 'BU', 13)
    pdf.cell(0, 7, 'ATTENDANCE SUMMARY REPORT', align='C', ln=True)
    _set_text(pdf, MID)
    pdf.set_font('Arial', '', 9)
    parts = []
    if grade:  parts.append(f"Grade: {grade}")
    if stream: parts.append(f"Stream: {stream}")
    if term:   parts.append(f"Term: {term}")
    pdf.cell(0, 5, '   |   '.join(parts) or 'All', align='C', ln=True)
    pdf.ln(5)

    # KPI strip
    kpis = [
        ('Total Days Recorded', total_days, ''),
        ('Total Students',      len(students), ''),
        ('Class Avg Rate',      f"{avg_rate}%", ''),
        ('Below 80%',           len(poor_attendance), 'students'),
    ]
    kpi_clrs = [NAVY,(0,100,80),(120,60,0),CRIMSON]
    for (label,val,sub),col in zip(kpis, kpi_clrs):
        _mini_kpi(pdf, label, val, sub, fill=col)
    pdf.ln(22)
    _gold_divider(pdf)

    # Full attendance table
    draw_section_title(pdf, "Student Attendance Details")
    a_cols = [('Reg No',28),('Name',65),('Grade',18),('Stream',18),
              ('Days Present',25),('Total Days',20),('Rate %',20),('Status',16)]
    draw_styled_table_header(pdf, a_cols)
    a_widths = [w for _, w in a_cols]

    for idx, r in enumerate(rows_sorted):
        sclr  = CRIMSON if r['flag'] else GREEN
        fill  = (255,240,240) if r['flag'] else (SKY if idx % 2 == 0 else WHITE)
        _set_fill(pdf, fill)
        _set_draw(pdf, (210,220,230))
        pdf.set_font('Arial', '', 7)
        _set_text(pdf, BLACK)
        pdf.cell(a_widths[0], 6, r['reg'],   border=1, align='L', fill=True)
        pdf.cell(a_widths[1], 6, r['name'],  border=1, align='L', fill=True)
        pdf.cell(a_widths[2], 6, r['grade'], border=1, align='C', fill=True)
        pdf.cell(a_widths[3], 6, r['stream'] or '-', border=1, align='C', fill=True)
        pdf.cell(a_widths[4], 6, str(r['days_present']), border=1, align='C', fill=True)
        pdf.cell(a_widths[5], 6, str(total_days),        border=1, align='C', fill=True)
        _set_text(pdf, sclr)
        pdf.set_font('Arial', 'B', 7)
        pdf.cell(a_widths[6], 6, f"{r['rate']}%", border=1, align='C', fill=True)
        pdf.cell(a_widths[7], 6, 'LOW' if r['flag'] else 'OK', border=1, align='C', fill=True)
        pdf.ln()
    _set_text(pdf, BLACK)

    # Poor attendance list
    if poor_attendance:
        pdf.ln(5)
        draw_section_title(pdf, f"Students Requiring Attention – Below 80% Attendance ({len(poor_attendance)})")
        pa_cols = [('Reg No',28),('Name',80),('Days Present',30),('Rate %',25),('Missing Days',30)]
        draw_styled_table_header(pdf, pa_cols)
        pa_w = [w for _, w in pa_cols]
        for idx, r in enumerate(sorted(poor_attendance, key=lambda x: x['rate'])):
            missing = r['total_days'] - r['days_present']
            fill = (255,240,240) if idx % 2 == 0 else WHITE
            _set_fill(pdf, fill)
            _set_draw(pdf, (210,220,230))
            pdf.set_font('Arial', '', 7)
            _set_text(pdf, BLACK)
            pdf.cell(pa_w[0], 6, r['reg'],  border=1, align='L', fill=True)
            pdf.cell(pa_w[1], 6, r['name'], border=1, align='L', fill=True)
            pdf.cell(pa_w[2], 6, str(r['days_present']), border=1, align='C', fill=True)
            _set_text(pdf, CRIMSON)
            pdf.set_font('Arial', 'B', 7)
            pdf.cell(pa_w[3], 6, f"{r['rate']}%", border=1, align='C', fill=True)
            pdf.cell(pa_w[4], 6, str(missing),     border=1, align='C', fill=True)
            pdf.ln()
        _set_text(pdf, BLACK)

    pdf_footer(pdf)
    safe = lambda s: s.replace(' ','_') if s else 'all'
    resp = HttpResponse(pdf.output(dest='S').encode('latin1'), content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="attendance_summary_{safe(grade)}_{safe(term)}.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# 7.  LEAVE ANALYSIS REPORT
# GET /reports/leave_analysis/?grade=Grade7&term=Term1&start_date=2024-01-01&end_date=2024-04-30
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def leave_analysis_report(request):
    """
    Leave management analytics:
      • Status breakdown (Approved / Pending / Rejected)
      • Reason distribution
      • Grade-wise leave counts
      • Full detail table
    Filters: grade, term, start_date, end_date
    """
    school_id  = request.user.school_id
    messages.get_messages(request).used = True

    grade      = request.GET.get('grade', '')
    term       = request.GET.get('term', '')
    start_date = request.GET.get('start_date', '')
    end_date   = request.GET.get('end_date', '')

    def parse_date(s):
        try: return datetime.strptime(s, '%Y-%m-%d').date() if s else None
        except: return None

    start = parse_date(start_date)
    end   = parse_date(end_date)

    lv_qs = LeaveManagement.objects.filter(school_id=school_id).select_related('registration_no')
    if grade: lv_qs = lv_qs.filter(registration_no__grade=grade)
    if term:  lv_qs = lv_qs.filter(term=term)
    if start: lv_qs = lv_qs.filter(date_of_leave__gte=start)
    if end:   lv_qs = lv_qs.filter(date_of_leave__lte=end)
    lv_qs = lv_qs.order_by('-date_of_leave')

    leaves = list(lv_qs)

    # Aggregate
    status_counts = defaultdict(int)
    reason_counts = defaultdict(int)
    grade_counts  = defaultdict(int)
    for lv in leaves:
        status_counts[(lv.status or 'Pending').capitalize()] += 1
        reason_counts[lv.reason or 'Other'] += 1
        grade_counts[getattr(lv.registration_no, 'grade', '-')] += 1

    total = len(leaves) or 1

    # ── PDF ──────────────────────────────────────────────────────────────────
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf_header(request, pdf, 30)

    _set_text(pdf, NAVY)
    pdf.set_font('Arial', 'BU', 13)
    pdf.cell(0, 7, 'LEAVE ANALYSIS REPORT', align='C', ln=True)
    _set_text(pdf, MID)
    pdf.set_font('Arial', '', 9)
    date_lbl = f"{start.strftime('%d/%m/%Y') if start else 'All'} - {end.strftime('%d/%m/%Y') if end else 'All'}"
    pdf.cell(0, 5, f"Period: {date_lbl}   |   Term: {term or 'All'}   |   Grade: {grade or 'All'}", align='C', ln=True)
    pdf.ln(5)

    # KPI strip
    kpis = [
        ('Total Leaves',  len(leaves), ''),
        ('Approved',      status_counts.get('Approved',0), ''),
        ('Pending',       status_counts.get('Pending',0),  ''),
        ('Rejected',      status_counts.get('Rejected',0), ''),
    ]
    kpi_clrs = [NAVY, GREEN, (180,120,0), CRIMSON]
    for (label,val,sub),col in zip(kpis,kpi_clrs):
        _mini_kpi(pdf, label, val, sub, fill=col)
    pdf.ln(22)
    _gold_divider(pdf)

    # Status distribution bar
    draw_section_title(pdf, "Leave Status Distribution")
    bar_w = pdf.w - pdf.l_margin - pdf.r_margin - 30
    for status, cnt in status_counts.items():
        pct = round(cnt/total*100, 1)
        sclr = {'Approved':GREEN,'Pending':(180,120,0),'Rejected':CRIMSON}.get(status, NAVY)
        _set_text(pdf, sclr)
        pdf.set_font('Arial', 'B', 7)
        pdf.set_x(pdf.l_margin)
        pdf.cell(25, 6, status)
        _progress_bar(pdf, pdf.get_x(), pdf.get_y()+1, bar_w, 4, pct, sclr)
        pdf.set_x(pdf.get_x() + bar_w + 2)
        _set_text(pdf, BLACK)
        pdf.set_font('Arial', '', 6)
        pdf.cell(25, 6, f"{cnt} ({pct}%)", ln=True)

    # Reason breakdown
    pdf.ln(4)
    draw_section_title(pdf, "Leave Reason Breakdown")
    r_cols = [('Reason', 80), ('Count', 25), ('Percentage', 30)]
    draw_styled_table_header(pdf, r_cols)
    r_widths = [w for _, w in r_cols]
    for idx, (reason, cnt) in enumerate(sorted(reason_counts.items(), key=lambda x: -x[1])):
        pct  = round(cnt/total*100,1)
        fill = SKY if idx % 2 == 0 else WHITE
        _set_fill(pdf, fill)
        _set_draw(pdf, (210,220,230))
        pdf.set_font('Arial', '', 7)
        _set_text(pdf, BLACK)
        pdf.cell(r_widths[0], 6, reason,    border=1, align='L', fill=True)
        pdf.cell(r_widths[1], 6, str(cnt),  border=1, align='C', fill=True)
        pdf.cell(r_widths[2], 6, f"{pct}%", border=1, align='C', fill=True)
        pdf.ln()
    _set_text(pdf, BLACK)

    # Grade-wise counts
    pdf.ln(4)
    draw_section_title(pdf, "Leaves by Grade")
    g_cols = [('Grade', 50), ('Leave Count', 30), ('% of Total', 30)]
    draw_styled_table_header(pdf, g_cols)
    g_widths = [w for _, w in g_cols]
    for idx, (g, cnt) in enumerate(sorted(grade_counts.items())):
        pct  = round(cnt/total*100,1)
        fill = SKY if idx % 2 == 0 else WHITE
        _set_fill(pdf, fill)
        _set_draw(pdf, (210,220,230))
        pdf.set_font('Arial', '', 7)
        _set_text(pdf, BLACK)
        pdf.cell(g_widths[0], 6, g,         border=1, align='L', fill=True)
        pdf.cell(g_widths[1], 6, str(cnt),  border=1, align='C', fill=True)
        pdf.cell(g_widths[2], 6, f"{pct}%", border=1, align='C', fill=True)
        pdf.ln()
    _set_text(pdf, BLACK)

    # Full leave detail table
    pdf.ln(4)
    draw_section_title(pdf, "Leave Detail Records")
    d_cols = [('Date',22),('Reg No',25),('Name',55),('Grade',18),
              ('Reason',30),('Return',22),('Status',22)]
    draw_styled_table_header(pdf, d_cols)
    d_widths = [w for _, w in d_cols]
    for idx, lv in enumerate(leaves):
        s     = lv.registration_no
        name  = f"{getattr(s,'first_name','')} {getattr(s,'surname','')}".strip()
        status = (lv.status or 'Pending').capitalize()
        sclr  = {'Approved':GREEN,'Pending':(180,120,0),'Rejected':CRIMSON}.get(status, BLACK)
        fill  = SKY if idx % 2 == 0 else WHITE
        _set_fill(pdf, fill)
        _set_draw(pdf, (210,220,230))
        pdf.set_font('Arial', '', 6)
        _set_text(pdf, BLACK)
        pdf.cell(d_widths[0], 5, str(lv.date_of_leave or '-'), border=1, align='C', fill=True)
        pdf.cell(d_widths[1], 5, str(s.registration_no),       border=1, align='L', fill=True)
        pdf.cell(d_widths[2], 5, name[:26],                    border=1, align='L', fill=True)
        pdf.cell(d_widths[3], 5, getattr(s,'grade',''),        border=1, align='C', fill=True)
        pdf.cell(d_widths[4], 5, str(lv.reason or 'Other')[:16], border=1, align='L', fill=True)
        pdf.cell(d_widths[5], 5, str(lv.return_date or '-'),   border=1, align='C', fill=True)
        _set_text(pdf, sclr)
        pdf.set_font('Arial', 'B', 6)
        pdf.cell(d_widths[6], 5, status, border=1, align='C', fill=True)
        pdf.ln()
    _set_text(pdf, BLACK)

    pdf_footer(pdf)
    safe = lambda s: s.replace(' ','_') if s else 'all'
    resp = HttpResponse(pdf.output(dest='S').encode('latin1'), content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="leave_analysis_{safe(grade)}_{safe(term)}.pdf"'
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# 8.  COMPETENCY HEATMAP REPORT
# GET /reports/competency_heatmap/?grade=Grade7&term=Term1&year=2024
# ─────────────────────────────────────────────────────────────────────────────
@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def competency_heatmap_report(request):
    """
    Grid report showing avg competency level for each
    Subject × Core-Competency combination, heat-coloured by level.
    Filters: grade, stream, term, year
    """
    school_id = request.user.school_id
    messages.get_messages(request).used = True

    grade  = request.GET.get('grade', '')
    stream = request.GET.get('stream', '')
    term   = request.GET.get('term', '')
    year   = request.GET.get('year', str(datetime.now().year))

    base_q = Q(student__school_id=school_id)
    if grade:  base_q &= Q(student__grade=grade)
    if stream: base_q &= Q(student__stream=stream)
    if term:   base_q &= Q(term=term)
    if year:   base_q &= Q(year=year)

    comp_qs = (
        LearnerCompetency.objects.filter(base_q)
        .values('subject','competency')
        .annotate(avg_level=Avg('level'), count=Count('id'))
    )

    # Build grid {subject: {competency: avg_level}}
    grid     = defaultdict(dict)
    subjects = set()
    for r in comp_qs:
        subj = r['subject']
        comp = r['competency']
        subjects.add(subj)
        grid[subj][comp] = round(r['avg_level'] or 0, 2)

    # School avg per competency
    comp_school_avg = {}
    for comp in core_competencies:
        vals = [grid[s].get(comp, 0) for s in subjects if grid[s].get(comp, 0) > 0]
        comp_school_avg[comp] = round(sum(vals)/len(vals), 2) if vals else 0

    def _heat_color(level):
        """Return RGB fill based on 1-4 level scale."""
        if level >= 3.5:  return GREEN
        if level >= 2.5:  return (0, 140, 100)
        if level >= 1.5:  return (180, 120, 0)
        if level > 0:     return CRIMSON
        return (200, 200, 200)

    # ── PDF (Landscape) ───────────────────────────────────────────────────────
    pdf = FPDF(orientation='L')
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf_header(request, pdf, 30)

    _set_text(pdf, NAVY)
    pdf.set_font('Arial', 'BU', 13)
    pdf.cell(0, 7, 'COMPETENCY HEATMAP REPORT', align='C', ln=True)
    _set_text(pdf, MID)
    pdf.set_font('Arial', '', 9)
    parts = []
    if grade:  parts.append(f"Grade: {grade}")
    if stream: parts.append(f"Stream: {stream}")
    if term:   parts.append(f"Term: {term}")
    parts.append(f"Year: {year}")
    pdf.cell(0, 5, '   |   '.join(parts), align='C', ln=True)
    pdf.ln(5)

    # Legend
    draw_section_title(pdf, "Heat Level Legend")
    for label, col, lv_range in [
        ('EE – Exceeding (3.5–4.0)', GREEN,           '3.5–4.0'),
        ('ME – Meeting (2.5–3.4)',   (0,140,100),     '2.5–3.4'),
        ('AE – Approaching (1.5–2.4)',(180,120,0),   '1.5–2.4'),
        ('BE – Below (0–1.4)',        CRIMSON,         '0.0–1.4'),
        ('No Data',                   (200,200,200),  '-'),
    ]:
        _set_fill(pdf, col)
        pdf.rect(pdf.get_x(), pdf.get_y()+1, 8, 4, style='F')
        pdf.set_x(pdf.get_x() + 10)
        _set_text(pdf, BLACK)
        pdf.set_font('Arial', '', 7)
        pdf.cell(70, 6, label)
    pdf.ln(8)

    # Heatmap grid
    draw_section_title(pdf, "Subject × Competency Average Level Grid")

    avail_w = pdf.w - pdf.l_margin - pdf.r_margin
    subj_col_w = 40
    comp_col_w = round((avail_w - subj_col_w) / max(len(core_competencies), 1), 1)

    # Header row
    _set_fill(pdf, NAVY)
    _set_text(pdf, GOLD)
    pdf.set_font('Arial', 'B', 5)
    pdf.cell(subj_col_w, 8, 'Learning Area', border=0, fill=True, align='C')
    for comp in core_competencies:
        abbr = comp[:12]
        pdf.cell(comp_col_w, 8, abbr, border=0, fill=True, align='C')
    pdf.ln()

    # Data rows
    for idx, subj in enumerate(sorted(subjects)):
        bg = (245,249,255) if idx % 2 == 0 else WHITE
        _set_fill(pdf, bg)
        _set_text(pdf, NAVY)
        pdf.set_font('Arial', 'B', 5)
        pdf.cell(subj_col_w, 6, subj[:20], border=1, fill=True, align='L')
        for comp in core_competencies:
            lv   = grid[subj].get(comp, 0)
            hclr = _heat_color(lv)
            _set_fill(pdf, hclr)
            _set_text(pdf, WHITE)
            pdf.set_font('Arial', 'B', 5)
            pdf.cell(comp_col_w, 6, str(lv) if lv else '-', border=1, fill=True, align='C')
        pdf.ln()

    # School avg row
    _set_fill(pdf, NAVY)
    _set_text(pdf, GOLD)
    pdf.set_font('Arial', 'B', 6)
    pdf.cell(subj_col_w, 7, 'SCHOOL AVG', border=1, fill=True, align='C')
    for comp in core_competencies:
        avg = comp_school_avg.get(comp, 0)
        hclr = _heat_color(avg)
        _set_fill(pdf, hclr)
        _set_text(pdf, WHITE)
        pdf.set_font('Arial', 'B', 6)
        pdf.cell(comp_col_w, 7, str(avg) if avg else '-', border=1, fill=True, align='C')
    pdf.ln(8)
    _set_text(pdf, BLACK)

    # Competency ranking table
    pdf.ln(3)
    draw_section_title(pdf, "Competency Strength Ranking (School-wide avg)")
    ranked_comps = sorted(core_competencies, key=lambda c: comp_school_avg.get(c,0), reverse=True)
    cr_cols = [('#',12),('Competency',70),('School Avg Level',35),('Band',20),('Strength',55)]
    draw_styled_table_header(pdf, cr_cols)
    cr_w = [w for _, w in cr_cols]
    for pos, comp in enumerate(ranked_comps, 1):
        avg  = comp_school_avg.get(comp, 0)
        band = _cbc_band(avg)
        bclr = {'EE':GREEN,'ME':NAVY,'AE':(180,120,0),'BE':CRIMSON}.get(band, BLACK)
        fill = SKY if pos % 2 == 0 else WHITE
        _set_fill(pdf, fill)
        _set_draw(pdf, (210,220,230))
        pdf.set_font('Arial', 'B', 7)
        _set_text(pdf, GOLD if pos <= 3 else BLACK)
        pdf.cell(cr_w[0], 6, str(pos), border=1, align='C', fill=True)
        _set_text(pdf, BLACK)
        pdf.set_font('Arial', '', 7)
        pdf.cell(cr_w[1], 6, comp,      border=1, align='L', fill=True)
        pdf.cell(cr_w[2], 6, str(avg),  border=1, align='C', fill=True)
        _set_text(pdf, bclr)
        pdf.set_font('Arial', 'B', 7)
        pdf.cell(cr_w[3], 6, band,      border=1, align='C', fill=True)
        _set_text(pdf, BLACK)
        pdf.set_font('Arial', '', 6)
        # mini bar
        bx = pdf.get_x() + 1
        by = pdf.get_y() + 2
        _progress_bar(pdf, bx, by, cr_w[4]-2, 3, avg/4*100, bclr)
        pdf.cell(cr_w[4], 6, '', border=1, fill=False)
        pdf.ln()
    _set_text(pdf, BLACK)

    pdf_footer(pdf)
    safe = lambda s: s.replace(' ','_') if s else 'all'
    resp = HttpResponse(pdf.output(dest='S').encode('latin1'), content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="competency_heatmap_{safe(grade)}_{safe(term)}.pdf"'
    return resp