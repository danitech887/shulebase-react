from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models.functions import ExtractMonth, ExtractYear
from django.shortcuts import get_object_or_404
from models import RegConfig, MasterSchool, StudentInfo


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def registration_config_view(request):
    school_id = request.user.school_id
    school_instance = get_object_or_404(MasterSchool, id=school_id)

    if request.method == 'GET':
        reg_config_obj = RegConfig.objects.filter(school=school_instance, target_type='student').first()
        current_format = reg_config_obj.reg_format if reg_config_obj else ''

        # Fetch existing registration numbers to generate the next one
        existing_regnos = set(StudentInfo.objects.filter(school_id=school_id).values_list('registration_no', flat=True))
        next_reg_no = get_next_registration_number(school_id, existing_regnos)

        return Response({
            'current_format': current_format,
            'next_registration_number': next_reg_no
        })

    elif request.method == 'POST':
        reg_format = request.data.get('reg_format')
        if not reg_format:
            return Response({'error': 'Registration format is required.'}, status=400)

        if '/' in reg_format:
            return Response({'error': 'Invalid registration format. Use (-) instead of /'}, status=400)

        reg_config_obj, created = RegConfig.objects.update_or_create(
            school=school_instance,
            target_type='student',
            defaults={'reg_format': reg_format}
        )
        return Response({'message': f'Registration format updated to {reg_format}', 'current_format': reg_format})



        return Response({'message': f'Registration format updated to {reg_format}', 'current_format': reg_format})
