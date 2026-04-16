from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django.db.models import Q
from core.models import Reviews
from core.serializers import ReviewsSerializer

class ReviewsListCreateView(generics.ListCreateAPIView):
    """
    GET: System Owners see all; others see only approved ones or their own.
    POST: Create a review (auto-populate school and author).
    """
    serializer_class = ReviewsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        # System Owners see all
        if user.role == 'SystemOwner' or user.is_superuser:
            return Reviews.objects.all().order_by('-created_at')
        
        # General users see approved ones OR their own
        return Reviews.objects.filter(
            Q(is_approved=True) | Q(created_by=user)
        ).order_by('-created_at')

    def perform_create(self, serializer):
        user = self.request.user
        # Normalize role to match USER_TYPES choices (teacher, student, parent, Admin)
        u_type = user.role
        if u_type and u_type.lower() == 'teacher': u_type = 'teacher'
        elif u_type and u_type.lower() == 'student': u_type = 'student'
        elif u_type and u_type.lower() == 'parent': u_type = 'parent'
        elif u_type and u_type.lower() == 'admin': u_type = 'Admin'

        serializer.save(
            created_by=user,
            school_id=user.school_id,
            full_name=user.username,
            user_type=u_type or 'student'
        )

class ReviewsDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    PATCH: 
    - Owner can update content/rating/location.
    - System Owner can update is_approved.
    DELETE: Owner or System Owner.
    """
    serializer_class = ReviewsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # Allow system owner to access any record for approval/deletion
        if user.role == 'SystemOwner' or user.is_superuser:
            return Reviews.objects.all()
        # Users can only access their own records for detail view/update/delete
        return Reviews.objects.filter(created_by=user)

    def perform_update(self, serializer):
        user = self.request.user
        instance = self.get_object()
        
        # If toggling approval, check if System Owner
        if 'is_approved' in self.request.data:
            if not (user.role == 'SystemOwner' or user.is_superuser):
                raise PermissionDenied("Only system owners can approve reviews.")
        
        # If updating content, check if owner
        if any(f in self.request.data for f in ['content', 'rating', 'location']):
             if instance.created_by != user and not (user.role == 'SystemOwner' or user.is_superuser):
                  raise PermissionDenied("You can only edit your own reviews.")
                  
        serializer.save()


class PublicReviewsListView(generics.ListAPIView):
    """
    Publicly accessible list of approved reviews.
    """
    queryset = Reviews.objects.filter(is_approved=True).order_by('-created_at')
    serializer_class = ReviewsSerializer
    permission_classes = [permissions.AllowAny]
