from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django.db.models import Q
from core.models import Announcement
from core.serializers import AnnouncementSerializer

class AnnouncementListCreateView(generics.ListCreateAPIView):
    """
    GET: List announcements filtered by school and audience (Admin sees all; Teachers/Students see targeted).
    POST: Create a new announcement (Admin only).
    """
    serializer_class = AnnouncementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        school_id = user.school_id
        
        # Base: results for this school
        qs = Announcement.objects.filter(school_id=school_id)
        
        # If not Admin, filter by audience
        if user.role.lower() != 'admin':
            # Map system role to audience labels
            role_label = user.role
            if user.role.lower() == 'teacher': role_label = 'Teachers'
            if user.role.lower() == 'student': role_label = 'Students'
            
            qs = qs.filter(Q(target_audience__icontains=role_label) | Q(target_audience__icontains='All'))
            
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        if self.request.user.role.lower() != 'admin':
            raise PermissionDenied("Only school admins can create announcements.")
        serializer.save(school_id=self.request.user.school_id, created_by=self.request.user)


class AnnouncementDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET: View details of an announcement.
    PATCH/PUT: Update announcement (Admin only).
    DELETE: Remove announcement (Admin only).
    """
    serializer_class = AnnouncementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Announcement.objects.filter(school_id=self.request.user.school_id)

    def perform_update(self, serializer):
        if self.request.user.role.lower() != 'admin':
            raise PermissionDenied("Only school admins can edit announcements.")
        serializer.save()

    def perform_destroy(self, instance):
        if self.request.user.role.lower() != 'admin':
            raise PermissionDenied("Only school admins can delete announcements.")
        instance.delete()
