from rest_framework import serializers
from apps.identity.models import User
from apps.support.models import (
    EscalationStageChoices,
    Ticket,
    TicketActivity,
    TicketAttachment,
    TicketCategoryChoices,
    TicketMessage,
    TicketPriorityChoices,
    TicketStatusChoices,
)


class UserBasicSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'role']

    def get_full_name(self, obj):
        name = f"{obj.first_name} {obj.last_name}".strip()
        return name or obj.email.split('@')[0]

    def get_role(self, obj):
        if hasattr(obj, 'staff_profile') and obj.staff_profile and obj.staff_profile.staff_role:
            return obj.staff_profile.staff_role.name
        roles = obj.roles
        return roles[0] if roles else ''


class TicketAttachmentSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()
    uploader_email = serializers.CharField(source='uploader.email', read_only=True)

    class Meta:
        model = TicketAttachment
        fields = [
            'id',
            'file_name',
            'file_size',
            'content_type',
            'is_internal',
            'download_url',
            'uploader_email',
            'created_at',
        ]

    def get_download_url(self, obj):
        return f"/api/v1/support/attachments/{obj.id}/"


class TicketMessageSerializer(serializers.ModelSerializer):
    sender_email = serializers.CharField(source='sender.email', read_only=True)
    sender_name = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()

    class Meta:
        model = TicketMessage
        fields = [
            'id',
            'sender_email',
            'sender_name',
            'sender_type',
            'message',
            'is_internal',
            'attachments',
            'created_at',
        ]

    def get_sender_name(self, obj):
        if not obj.sender:
            return "System"
        name = f"{obj.sender.first_name} {obj.sender.last_name}".strip()
        return name or obj.sender.email.split('@')[0]

    def get_attachments(self, obj):
        request = self.context.get('request')
        is_staff = request and (
            getattr(request.user, 'is_superuser', False)
            or getattr(request.user, 'role', '') == 'ADMIN'
            or (hasattr(request.user, 'has_permission') and request.user.has_permission('support.ticket.manage'))
        )
        qs = obj.attachments.all()
        if not is_staff:
            qs = qs.filter(is_internal=False)
        return TicketAttachmentSerializer(qs, many=True, context=self.context).data


class TicketActivitySerializer(serializers.ModelSerializer):
    actor_email = serializers.CharField(source='actor.email', read_only=True)

    class Meta:
        model = TicketActivity
        fields = [
            'id',
            'activity_type',
            'actor_email',
            'old_value',
            'new_value',
            'notes',
            'created_at',
        ]


class CustomerTicketListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = [
            'id',
            'ticket_number',
            'subject',
            'category',
            'priority',
            'status',
            'related_order_number',
            'created_at',
            'updated_at',
        ]


class CustomerTicketDetailSerializer(serializers.ModelSerializer):
    messages = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()

    class Meta:
        model = Ticket
        fields = [
            'id',
            'ticket_number',
            'subject',
            'description',
            'category',
            'priority',
            'status',
            'related_order_number',
            'resolution_summary',
            'resolved_at',
            'closed_at',
            'messages',
            'attachments',
            'created_at',
            'updated_at',
        ]

    def get_messages(self, obj):
        # Strict isolation: Customers NEVER receive internal notes!
        public_msgs = obj.messages.filter(is_internal=False).select_related('sender').prefetch_related('attachments')
        return TicketMessageSerializer(public_msgs, many=True, context=self.context).data

    def get_attachments(self, obj):
        # Strict isolation: Customers NEVER receive internal attachments!
        public_atts = obj.attachments.filter(is_internal=False).select_related('uploader')
        return TicketAttachmentSerializer(public_atts, many=True, context=self.context).data


class StaffTicketListSerializer(serializers.ModelSerializer):
    customer = UserBasicSerializer(read_only=True)
    assigned_to = UserBasicSerializer(read_only=True)

    class Meta:
        model = Ticket
        fields = [
            'id',
            'ticket_number',
            'subject',
            'category',
            'priority',
            'status',
            'customer',
            'assigned_to',
            'related_order_number',
            'is_confidential',
            'first_response_due_at',
            'first_responded_at',
            'is_first_response_overdue',
            'resolution_due_at',
            'is_resolution_overdue',
            'sla_breached',
            'is_escalated',
            'escalation_stage',
            'created_at',
            'updated_at',
        ]


class StaffTicketDetailSerializer(serializers.ModelSerializer):
    customer = UserBasicSerializer(read_only=True)
    assigned_to = UserBasicSerializer(read_only=True)
    assigned_by = UserBasicSerializer(read_only=True)
    resolved_by = UserBasicSerializer(read_only=True)
    messages = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()
    activities = TicketActivitySerializer(many=True, read_only=True)

    class Meta:
        model = Ticket
        fields = [
            'id',
            'ticket_number',
            'subject',
            'description',
            'category',
            'priority',
            'status',
            'customer',
            'assigned_to',
            'assigned_by',
            'assigned_at',
            'related_order_number',
            'is_confidential',
            'first_response_due_at',
            'first_responded_at',
            'is_first_response_overdue',
            'resolution_due_at',
            'resolved_at',
            'resolved_by',
            'is_resolution_overdue',
            'sla_paused_at',
            'total_paused_seconds',
            'sla_breached',
            'is_escalated',
            'escalation_stage',
            'escalated_at',
            'escalation_reason',
            'resolution_summary',
            'reopen_count',
            'closed_at',
            'messages',
            'attachments',
            'activities',
            'created_at',
            'updated_at',
        ]

    def get_messages(self, obj):
        # Staff can view all messages including internal notes
        all_msgs = obj.messages.all().select_related('sender').prefetch_related('attachments')
        return TicketMessageSerializer(all_msgs, many=True, context=self.context).data

    def get_attachments(self, obj):
        all_atts = obj.attachments.all().select_related('uploader')
        return TicketAttachmentSerializer(all_atts, many=True, context=self.context).data


class CreateTicketPayloadSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=255, min_length=5)
    description = serializers.CharField(min_length=10)
    category = serializers.ChoiceField(choices=TicketCategoryChoices.choices, default=TicketCategoryChoices.GENERAL_INQUIRY)
    priority = serializers.ChoiceField(choices=TicketPriorityChoices.choices, default=TicketPriorityChoices.MEDIUM)
    related_order_number = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')


class TicketMessagePayloadSerializer(serializers.Serializer):
    message = serializers.CharField(min_length=1)
    is_internal = serializers.BooleanField(default=False)


class UpdateTicketStatusPayloadSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=TicketStatusChoices.choices)
    resolution_summary = serializers.CharField(required=False, allow_blank=True, default='')
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class AssignTicketPayloadSerializer(serializers.Serializer):
    agent_id = serializers.UUIDField(required=False, allow_null=True)


class EscalateTicketPayloadSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=5)
    stage = serializers.ChoiceField(choices=EscalationStageChoices.choices, default=EscalationStageChoices.TIER_3)
