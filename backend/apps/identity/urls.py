from django.urls import path
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
    StaffTokenRefreshView,
    StaffMemberListView,
    StaffMemberDetailView,
    StaffRoleListView,
    StaffMetricsView,
    StaffInvitationListView,
    StaffInvitationResendView,
    StaffInvitationRevokeView,
    ApprovalRequestListView,
    ApprovalRequestDetailView,
    ApprovalRequestApproveView,
    ApprovalRequestRejectView,
    ApprovalRequestCancelView,
    ApprovalRequestExecuteView,
)

urlpatterns = [
    # Auth endpoints
    path('auth/register/', RegisterView.as_view(), name='auth-register'),
    path('auth/login/', LoginView.as_view(), name='auth-login'),
    path('auth/logout/', LogoutView.as_view(), name='auth-logout'),
    path('auth/token/refresh/', StaffTokenRefreshView.as_view(), name='token-refresh'),
    path('auth/verify-email/', VerifyEmailView.as_view(), name='auth-verify-email'),
    path('auth/resend-verification/', ResendVerificationView.as_view(), name='auth-resend-verification'),
    path('auth/password-reset/request/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('auth/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('auth/switch-role/', SwitchRoleView.as_view(), name='auth-switch-role'),
    path('auth/mfa/enrol/', MFAEnrolView.as_view(), name='auth-mfa-enrol'),
    path('auth/mfa/verify/', MFAVerifyView.as_view(), name='auth-mfa-verify'),
    path('auth/staff/set-password/', StaffSetPasswordView.as_view(), name='auth-staff-set-password'),

    # Admin endpoints & Staff Administration
    path('admin/staff/', StaffMemberListView.as_view(), name='admin-staff-list'),
    path('admin/staff/roles/', StaffRoleListView.as_view(), name='admin-staff-roles'),
    path('admin/staff/metrics/', StaffMetricsView.as_view(), name='admin-staff-metrics'),
    path('admin/staff/invitations/', StaffInvitationListView.as_view(), name='admin-staff-invitations'),
    path('admin/staff/invitations/<str:pk>/resend/', StaffInvitationResendView.as_view(), name='admin-staff-invitation-resend'),
    path('admin/staff/invitations/<str:pk>/revoke/', StaffInvitationRevokeView.as_view(), name='admin-staff-invitation-revoke'),
    path('admin/staff/invite/', StaffInviteView.as_view(), name='admin-staff-invite'),
    path('admin/staff/<str:pk>/', StaffMemberDetailView.as_view(), name='admin-staff-detail'),

    # Maker-Checker Dual Authorization Approvals
    path('admin/approvals/', ApprovalRequestListView.as_view(), name='admin-approvals-list'),
    path('admin/approvals/<str:pk>/', ApprovalRequestDetailView.as_view(), name='admin-approvals-detail'),
    path('admin/approvals/<str:pk>/approve/', ApprovalRequestApproveView.as_view(), name='admin-approvals-approve'),
    path('admin/approvals/<str:pk>/reject/', ApprovalRequestRejectView.as_view(), name='admin-approvals-reject'),
    path('admin/approvals/<str:pk>/cancel/', ApprovalRequestCancelView.as_view(), name='admin-approvals-cancel'),
    path('admin/approvals/<str:pk>/execute/', ApprovalRequestExecuteView.as_view(), name='admin-approvals-execute'),

    # User profile endpoints
    path('users/me/', UserProfileView.as_view(), name='user-profile-me'),
]
