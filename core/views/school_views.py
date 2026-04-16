from rest_framework import permissions, generics
from core.serializers import SchoolRegistrationSerializer, PublicSchoolSerializer
from core.models import MasterSchool

class SchoolRegistrationView(generics.CreateAPIView):
    """Handles POST request for school registration."""
    queryset = MasterSchool.objects.all()
    serializer_class = SchoolRegistrationSerializer
    permission_classes = [permissions.AllowAny]
 
class SchoolUpdateView(generics.RetrieveUpdateAPIView):
    """Handles GET and PATCH/PUT for the school instance."""
    serializer_class = SchoolRegistrationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        # Maps to your logic: request.user.school_id
        return MasterSchool.objects.get(id=self.request.user.school_id)

class PublicSchoolListView(generics.ListAPIView):
    """
    Publicly accessible list of all registered schools.
    """
    queryset = MasterSchool.objects.all().order_by('school_name')
    serializer_class = PublicSchoolSerializer
    permission_classes = [permissions.AllowAny]