from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from core.models import Users, MasterSchool
from core.models import TeachersRole
from core.serializers import UserSerializer


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    """
    Login endpoint.
    POST /students/auth/login/
    
    Request:
    {
        "username": "admin",
        "password": "password123",
        "school_id": 1
    }
    
    Response:
    {
        "access": "token",
        "refresh": "token",
        "user": {username, school, school_id, school_name, role}
    }
    """
    username = request.data.get('username')
    password = request.data.get('password')

    if not username or not password:
        return Response({"error": "Username and password are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # First try Django's authenticate which will check hashed passwords
        user = authenticate(request, username=username, password=password)

        # If authenticate returns no user, fall back to Users lookup by username
        if not user:
            try:
                user = Users.objects.get(username=username)
            except Users.DoesNotExist:
                return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

            # Check password against hashed password field
            if not user.check_password(password):
                return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

        # Check if active
        if not getattr(user, 'is_active', True):
            return Response({"error": "User account is inactive"}, status=status.HTTP_401_UNAUTHORIZED)

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)

        user_data = {
            "id": user.id,
            "username": user.username,
            "school_id": getattr(user, 'school_id', None),
            "school_name": getattr(user, 'school_name', None),
            "role": getattr(user, 'role', None),
            "email": getattr(user, 'email', None),
            "registration_no": getattr(user, 'registration_no', None),
        }

        # Add is_class_teacher flag for teacher roles
        if user_data["role"] == 'Teacher' and user_data["registration_no"]:
            is_class_teacher = TeachersRole.objects.filter(
                school_id=user_data["school_id"],
                registration_no_id=user_data["registration_no"],
                type_of_teacher="Class Teacher"
            ).exists()
            user_data["is_class_teacher"] = is_class_teacher

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": user_data
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    """
    Register new user endpoint.
    POST /students/auth/register/
    
    Request:
    {
        "username": "teacher1",
        "password": "password123",
        "email": "teacher@school.com",
        "school_id": 1,
        "role": "teacher",
        "registration_no": "TCH001"
    }
    """
    username = request.data.get('username')
    password = request.data.get('password')
    email = request.data.get('email')
    school_id = request.data.get('school_id')
    role = request.data.get('role', 'teacher')
    registration_no = request.data.get('registration_no') # Frontend sends it as registration_no
    
    # Validate required fields
    if not all([username, password, email, school_id]):
        return Response(
            {"error": "username, password, email, and school_id are required"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if username already exists for this school
    if Users.objects.filter(username=username, school_id=school_id).exists():
        return Response(
            {"error": "Username already exists for this school"},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        school = MasterSchool.objects.get(id=school_id)
    except MasterSchool.DoesNotExist:
        return Response(
            {"error": "School not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        user = Users.objects.create_user(
            username=username,
            password=password,
            email=email,
            school=school,
            school_name=school.school_name,
            role=role,
            registration_no=registration_no
        )
        
        refresh = RefreshToken.for_user(user)
        
        return Response({
            "message": "User registered successfully",
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "username": user.username,
                "school_id": user.school_id,
                "school_name": user.school_name,
                "role": user.role,
                "email": user.email,
            }
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    """
    Logout endpoint (token invalidation).
    POST /students/auth/logout/
    
    Request:
    {
        "refresh": "refresh_token"
    }
    """
    try:
        refresh_token = request.data.get('refresh')
        if refresh_token:
            token = RefreshToken(refresh_token)
            token.blacklist()
        
        return Response(
            {"message": "Logged out successfully"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_current_user(request):
    """
    Get current authenticated user info.
    GET /students/auth/me/
    """
    user = request.user
    school = MasterSchool.objects.filter(id = user.school_id).first()
    print(school.school_name)
    return Response({
        "id": user.id,
        "username": user.username,
        "school_id": user.school_id,
        "school_name": school.school_name,
        "role": user.role,
        "email": user.email,
        "registration_no": user.registration_no,
    })



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """
    Change user password.
    POST /students/auth/change-password/
    
    Request:
    {
        "old_password": "current_password",
        "new_password": "new_secure_password",
        "confirm_password": "new_secure_password"
    }
    """
    user = request.user
    old_password = request.data.get('old_password')
    new_password = request.data.get('new_password')
    confirm_password = request.data.get('confirm_password')

    if not all([old_password, new_password, confirm_password]):
        return Response({"error": "All password fields are required."}, status=status.HTTP_400_BAD_REQUEST)

    if not user.check_password(old_password):
        return Response({"error": "Incorrect old password."}, status=status.HTTP_400_BAD_REQUEST)

    if new_password != confirm_password:
        return Response({"error": "New passwords do not match."}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(new_password)
    user.save()

    return Response({"message": "Password updated successfully."}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_username(request):
    """
    Change username for non-student users.
    POST /students/auth/change-username/
    
    Request:
    {
        "new_username": "new_username",
        "password": "current_password_to_confirm"
    }
    """
    user = request.user
    if user.role.lower() in ['student', 'parent']:
        return Response({"error": "You are not authorized to change your username."}, status=status.HTTP_403_FORBIDDEN)

    new_username = request.data.get('new_username')
    password = request.data.get('password')

    if not user.check_password(password):
        return Response({"error": "Incorrect password. Cannot verify identity."}, status=status.HTTP_400_BAD_REQUEST)

    if Users.objects.filter(username=new_username, school_id=user.school_id).exclude(pk=user.pk).exists():
        return Response({"error": "This username is already taken."}, status=status.HTTP_400_BAD_REQUEST)

    user.username = new_username
    user.save()

    return Response({"message": "Username updated successfully.", "user": UserSerializer(user).data}, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_schools(request):
    """
    Get list of all schools.
    GET /students/auth/schools/
    """
    try:
        schools = MasterSchool.objects.all()
        data = [
            {
                "id": school.id,
                "school_name": school.school_name,
                "contact": school.contact,
                "email_address": school.email_address,
            }
            for school in schools
        ]
        return Response(data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
