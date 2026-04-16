from django.urls import path
from core.views.school_views import SchoolRegistrationView, SchoolUpdateView, PublicSchoolListView
from core.views.announcement_views import AnnouncementListCreateView, AnnouncementDetailView
from core.views.review_views import ReviewsListCreateView, ReviewsDetailView, PublicReviewsListView

urlpatterns = [
    path('register/', SchoolRegistrationView.as_view(), name='school-register'),
    path('update/', SchoolUpdateView.as_view(), name='school-update'),
    
    # Public (No Auth Required for Home Page)
    path('public/reviews/', PublicReviewsListView.as_view(), name='public-reviews'),
    path('public/schools/', PublicSchoolListView.as_view(), name='public-schools'),

    # Announcements
    path('announcements/', AnnouncementListCreateView.as_view(), name='announcement-list'),
    path('announcements/<int:pk>/', AnnouncementDetailView.as_view(), name='announcement-detail'),

    # Reviews (Authenticated)
    path('reviews/', ReviewsListCreateView.as_view(), name='reviews-list'),
    path('reviews/<int:pk>/', ReviewsDetailView.as_view(), name='reviews-detail'),
]