from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from apps.onboarding.models import (
    SellerApplication,
    SellerApplicationStatusChoices,
    BusinessTypeChoices,
)
from apps.organisations.models import Organisation


class SellerApplicationSerializer(serializers.ModelSerializer):
    """Full detail serializer for seller applications."""

    applicant_email = serializers.EmailField(source='user.email', read_only=True)
    applicant_name = serializers.CharField(source='user.full_name', read_only=True)
    organisation_name = serializers.CharField(source='organisation.name', read_only=True, allow_null=True)
    reviewer_email = serializers.EmailField(source='reviewed_by.email', read_only=True, allow_null=True)

    class Meta:
        model = SellerApplication
        fields = [
            'id',
            'user',
            'applicant_email',
            'applicant_name',
            'organisation',
            'organisation_name',
            'business_name',
            'business_type',
            'company_registration_number',
            'tax_id',
            'contact_email',
            'contact_phone',
            'address_line1',
            'address_line2',
            'city',
            'postal_code',
            'country',
            'website_url',
            'description',
            'status',
            'submitted_at',
            'reviewed_by',
            'reviewer_email',
            'reviewed_at',
            'rejection_reason',
            'admin_notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'user',
            'status',
            'submitted_at',
            'reviewed_by',
            'reviewed_at',
            'rejection_reason',
            'admin_notes',
            'created_at',
            'updated_at',
        ]


class SellerApplicationCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for applicant creating or updating an application draft."""

    submit_now = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = SellerApplication
        fields = [
            'id',
            'organisation',
            'business_name',
            'business_type',
            'company_registration_number',
            'tax_id',
            'contact_email',
            'contact_phone',
            'address_line1',
            'address_line2',
            'city',
            'postal_code',
            'country',
            'website_url',
            'description',
            'submit_now',
        ]

    def validate_organisation(self, value):
        if value:
            user = self.context['request'].user
            if not value.is_member(user):
                raise serializers.ValidationError('You must be a member of the selected organisation.')
        return value

    def validate(self, attrs):
        user = self.context['request'].user

        # Prevent creating multiple approved or pending applications
        instance = getattr(self, 'instance', None)
        if not instance:
            if SellerApplication.objects.filter(user=user, status=SellerApplicationStatusChoices.APPROVED).exists():
                raise serializers.ValidationError('You already have an approved seller account.')

            if SellerApplication.objects.filter(user=user, status=SellerApplicationStatusChoices.PENDING).exists():
                raise serializers.ValidationError('You already have an application currently pending review.')
        else:
            if instance.status == SellerApplicationStatusChoices.APPROVED:
                raise serializers.ValidationError('Approved seller applications cannot be modified.')

        return attrs

    def create(self, validated_data):
        submit_now = validated_data.pop('submit_now', False)
        user = self.context['request'].user
        application = SellerApplication.objects.create(user=user, **validated_data)

        if submit_now:
            try:
                application.submit_for_review()
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else str(exc))

        return application

    def update(self, instance, validated_data):
        submit_now = validated_data.pop('submit_now', False)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if submit_now:
            try:
                instance.submit_for_review()
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.message_dict if hasattr(exc, 'message_dict') else str(exc))

        return instance


class SellerApplicationReviewSerializer(serializers.Serializer):
    """Serializer for staff/admin approving or rejecting seller applications."""

    action = serializers.ChoiceField(choices=['APPROVE', 'REJECT', 'approve', 'reject'])
    reason = serializers.CharField(required=False, allow_blank=True)
    rejection_reason = serializers.CharField(required=False, allow_blank=True)
    admin_notes = serializers.CharField(required=False, allow_blank=True)

    def to_internal_value(self, data):
        ret = super().to_internal_value(data)
        if 'action' in ret:
            ret['action'] = str(ret['action']).upper()
        if not ret.get('reason') and data.get('rejection_reason'):
            ret['reason'] = data['rejection_reason']
        return ret

    def validate(self, attrs):
        action = attrs.get('action')
        reason = (attrs.get('reason') or attrs.get('rejection_reason') or '').strip()

        if action == 'REJECT' and not reason:
            raise serializers.ValidationError({'reason': 'A rejection reason is required when rejecting an application.'})

        attrs['reason'] = reason
        return attrs
