from django.test import TestCase

# Create your tests here.
from django.shortcuts import render

# from backend.core.models import MasterSchool,Users
from ...backend.core.models import MasterSchool,Users


# class MasterSchool(models.Model):
#     school_name = models.CharField(max_length=100)
#     po_box = models.CharField(max_length=50)
#     address = models.CharField(max_length=100)
#     contact = models.CharField(max_length=20)
#     email_address = models.EmailField()

#     logo_path = models.ImageField(upload_to='school_logos/', blank=True, null=True)

#     created_at = models.DateTimeField(auto_now_add=True)
#     motto = models.CharField(max_length=255, blank=True, null=True)
#     vision = models.TextField(blank=True, null=True)
#     status_choices = ['Approved', 'Pending', 'Rejected']
#     status = models.CharField(max_length=20, choices=[(status, status) for status in status_choices], default='Pending')

#     class Meta:
#         verbose_name = "Master School"
#         db_table = 'school_info'
        
        

#     def __str__(self):
#         return self.school_name

MasterSchool.objects.create(
    school_name = 'DANITECH ACADEMY',
    po_box = '125-4083',
    address = 'Meru',
    contact = '254740338681',
    email_address = 'danitech@gmail.com',
    motto = 'Hard Work pays',
    vision = 'Aim Higher',
    status = 'Approved'
)

# class Users(AbstractBaseUser, PermissionsMixin):
#     username = models.CharField(max_length=50, unique=True)
#     school = models.ForeignKey(MasterSchool, on_delete=models.CASCADE, related_name="users")
#     school_name = models.CharField(max_length=100)
#     role = models.CharField(max_length=30)
#     registration_no = models.CharField(max_length=30, default="") 
#     email = models.EmailField(blank=True, null=True)
#     created_at = models.DateTimeField(auto_now_add=True)

#     is_active = models.BooleanField(default=True)
#     is_staff = models.BooleanField(default=False)
#     is_superuser = models.BooleanField(default=False)
#     last_login = models.DateTimeField(null=True)

#     USERNAME_FIELD = "username"
#     REQUIRED_FIELDS = ["email", "role", "school"]

#     objects = UserManager()

#     class Meta:
#         db_table = 'users'

#     def __str__(self):
#         return f"{self.username} ({self.role})"


# school_instance = MasterSchool.objects.get(id = 1)

# Users.objects.create(
#     username = 'danitech',
#     password = 'danitech',
#     school = school_instance,
#     role = 'Admin',
#     registration_no = '',
#     email = 'danitech@gmail.com',
#     is_superuser = True,
#     is_staff = True,

# )

