from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView,
    LoginView,
    LogoutView,
    UserProfileView,
    VerifyEmailView,
    ResendVerificationView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    SwitchRoleView,
    MFAEnrolView,
    MFAVerifyView,
    StaffInviteView,
    StaffSetPasswordView,
)

urlpatterns = [
    # Auth endpoints
    path('auth/register/', RegisterView.as_view(), name='auth-register'),
    path('auth/login/', LoginView.as_view(), name='auth-login'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('auth/verify-email/', VerifyEmailView.as_view(), name='auth-verify-email'),
    path('auth/resend-verification/', ResendVerificationView.as_view(), name='auth-resend-verification'),
    path('auth/password-reset/request/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('auth/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('auth/switch-role/', SwitchRoleView.as_view(), name='auth-switch-role'),
    path('auth/mfa/enrol/', MFAEnrolView.as_view(), name='auth-mfa-enrol'),
    path('auth/mfa/verify/', MFAVerifyView.as_view(), name='auth-mfa-verify'),
    path('auth/staff/set-password/', StaffSetPasswordView.as_view(), name='auth-staff-set-password'),

    # Admin endpoints
    path('admin/staff/invite/', StaffInviteView.as_view(), name='admin-staff-invite'),

    # User profile endpoints
    path('users/me/', UserProfileView.as_view(), name='user-profile-me'),
]
