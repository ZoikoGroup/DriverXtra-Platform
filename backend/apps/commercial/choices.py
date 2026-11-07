"""Controlled vocabularies for the commercial control plane (Master Architecture §4, §5, §9, §10, §21, §22)."""

from django.db import models


class VerticalChoices(models.TextChoices):
    VEHICLES = 'VEHICLES', 'Vehicle commerce'
    PARTS = 'PARTS', 'Parts & accessories'
    SERVICES = 'SERVICES', 'Workshop & services'
    EV = 'EV', 'EV Gateway'
    ROADSIDE = 'ROADSIDE', 'Roadside & assistance'
    FLEET = 'FLEET', 'FleetOps'
    B2B = 'B2B', 'Suppliers / OEM / B2B'
    ENTERPRISE_API = 'ENTERPRISE_API', 'Digital infrastructure / API'
    ADVERTISING = 'ADVERTISING', 'Advertising & demand'
    FINANCE_INSURANCE = 'FINANCE_INSURANCE', 'Finance / insurance (regulated)'


REGULATED_VERTICALS = {VerticalChoices.FINANCE_INSURANCE}


class SkuFamilyChoices(models.TextChoices):
    ADVERTISING = 'ADVERTISING', 'Advertising & listings'
    COMMERCE = 'COMMERCE', 'Commerce & bookings'
    SUBSCRIPTION = 'SUBSCRIPTION', 'Business SaaS subscription'
    REFERRAL = 'REFERRAL', 'Partner referral'
    REGULATED = 'REGULATED', 'Regulated introduction'
    API = 'API', 'API access'
    DATA = 'DATA', 'Data / insights'
    MARKETING = 'MARKETING', 'Partner campaigns'
    LOYALTY = 'LOYALTY', 'Loyalty administration'
    PAYMENT = 'PAYMENT', 'Payment-related margin'


REGULATED_SKU_FAMILIES = {SkuFamilyChoices.REGULATED, SkuFamilyChoices.PAYMENT}


class RevenueCodeChoices(models.TextChoices):
    ADV_01 = 'ADV-01', 'ADV-01 Vehicle listing fee / private seller'
    ADV_02 = 'ADV-02', 'ADV-02 Promoted listing / sponsored placement'
    ADV_03 = 'ADV-03', 'ADV-03 Dealer advertising plan'
    ADV_04 = 'ADV-04', 'ADV-04 Qualified dealer lead'
    COM_01 = 'COM-01', 'COM-01 Parts/accessories platform fee'
    COM_02 = 'COM-02', 'COM-02 Workshop booking facilitation'
    COM_03 = 'COM-03', 'COM-03 B2B procurement/wholesale'
    COM_04 = 'COM-04', 'COM-04 Vehicle closing service (future)'
    SUB_01 = 'SUB-01', 'SUB-01 Dealer SaaS subscription'
    SUB_02 = 'SUB-02', 'SUB-02 WorkshopHub subscription'
    SUB_03 = 'SUB-03', 'SUB-03 Supplier catalog / bulk tools'
    SUB_04 = 'SUB-04', 'SUB-04 FleetOps subscription'
    SUB_05 = 'SUB-05', 'SUB-05 OEM / enterprise software'
    REF_01 = 'REF-01', 'REF-01 EV installer/charging lead'
    REF_02 = 'REF-02', 'REF-02 Roadside, logistics, inspection'
    REG_01 = 'REG-01', 'REG-01 Consumer finance introduction'
    REG_02 = 'REG-02', 'REG-02 Insurance introduction'
    API_01 = 'API-01', 'API-01 API access / metered usage'
    DAT_01 = 'DAT-01', 'DAT-01 Aggregated insights / benchmarks'
    MKT_01 = 'MKT-01', 'MKT-01 Partner campaigns / co-marketing'
    LOY_01 = 'LOY-01', 'LOY-01 Partner-funded benefit administration'
    FIN_01 = 'FIN-01', 'FIN-01 Payment service-related margin'


# Revenue streams that are OFF / gated until separate legal, regulatory and board approval (§4, §8F, §13.7, D06).
GATED_REVENUE_CODES = {
    RevenueCodeChoices.REG_01,
    RevenueCodeChoices.REG_02,
    RevenueCodeChoices.FIN_01,
    RevenueCodeChoices.COM_04,
}


class FeeBasisChoices(models.TextChoices):
    FLAT_PER_UNIT = 'FLAT_PER_UNIT', 'Flat amount per unit'
    PERCENT_OF_BASE = 'PERCENT_OF_BASE', 'Percentage of commissionable base'
    RECURRING_FLAT = 'RECURRING_FLAT', 'Recurring flat amount per billing period'
    PER_ACCEPTED_LEAD = 'PER_ACCEPTED_LEAD', 'Per accepted qualified lead'
    PER_ACTIVE_ASSET = 'PER_ACTIVE_ASSET', 'Per active asset per period'
    USAGE_METERED = 'USAGE_METERED', 'Metered usage (not quotable in R1)'
    CUSTOM_CONTRACT = 'CUSTOM_CONTRACT', 'Custom contract pricing (not quotable in R1)'


FLAT_FEE_BASES = {
    FeeBasisChoices.FLAT_PER_UNIT,
    FeeBasisChoices.RECURRING_FLAT,
    FeeBasisChoices.PER_ACCEPTED_LEAD,
    FeeBasisChoices.PER_ACTIVE_ASSET,
}
QUOTABLE_FEE_BASES = FLAT_FEE_BASES | {FeeBasisChoices.PERCENT_OF_BASE}


class EntitlementTypeChoices(models.TextChoices):
    NONE = 'NONE', 'None'
    LISTING = 'LISTING', 'Listing'
    INVENTORY_SLOT = 'INVENTORY_SLOT', 'Inventory slot'
    SEAT = 'SEAT', 'Seat'
    ASSET = 'ASSET', 'Managed asset'
    SITE = 'SITE', 'Site / location'
    API_QUOTA = 'API_QUOTA', 'API quota'
    CAMPAIGN = 'CAMPAIGN', 'Campaign delivery'


class BillingIntervalChoices(models.TextChoices):
    ONE_TIME = 'ONE_TIME', 'One-time'
    PER_EVENT = 'PER_EVENT', 'Per earning event'
    MONTHLY = 'MONTHLY', 'Monthly'
    ANNUAL = 'ANNUAL', 'Annual'


class PayerRoleChoices(models.TextChoices):
    BUYER = 'BUYER', 'Buyer / driver'
    PRIVATE_SELLER = 'PRIVATE_SELLER', 'Private vehicle seller'
    DEALER = 'DEALER', 'Dealer'
    SUPPLIER = 'SUPPLIER', 'Parts supplier / distributor'
    WORKSHOP = 'WORKSHOP', 'Workshop / technician'
    EV_PARTNER = 'EV_PARTNER', 'EV charge / installation partner'
    FLEET = 'FLEET', 'Fleet / mobility operator'
    OEM_ENTERPRISE = 'OEM_ENTERPRISE', 'OEM / importer / enterprise'
    FINANCIAL_PARTNER = 'FINANCIAL_PARTNER', 'Finance / insurance provider'
    ADVERTISER = 'ADVERTISER', 'Advertiser / campaign partner'


class CatalogueStatusChoices(models.TextChoices):
    """Status for SKUs and rate schedules. Nothing binds unless APPROVED."""
    DRAFT = 'DRAFT', 'Draft'
    ILLUSTRATIVE = 'ILLUSTRATIVE', 'Illustrative (planning only, non-binding)'
    APPROVED = 'APPROVED', 'Approved'
    RETIRED = 'RETIRED', 'Retired'


class RoleProfileStatusChoices(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft'
    APPROVED = 'APPROVED', 'Approved'
    RETIRED = 'RETIRED', 'Retired'


class GateCapabilityChoices(models.TextChoices):
    DISCOVERY = 'DISCOVERY', 'Discovery & public pricing display'
    LEAD_CAPTURE = 'LEAD_CAPTURE', 'Consented lead capture'
    BINDING_QUOTE = 'BINDING_QUOTE', 'Binding quotes / transactions'
    SUBSCRIPTION_BILLING = 'SUBSCRIPTION_BILLING', 'Subscription billing'
    REGULATED_REFERRAL = 'REGULATED_REFERRAL', 'Regulated referral (finance/insurance)'


REGULATED_CAPABILITIES = {GateCapabilityChoices.REGULATED_REFERRAL}


class GateStatusChoices(models.TextChoices):
    DESIGNED = 'DESIGNED', 'Designed (closed)'
    LEGALLY_REVIEWED = 'LEGALLY_REVIEWED', 'Legally reviewed (closed)'
    PARTNER_VERIFIED = 'PARTNER_VERIFIED', 'Partner verified (closed)'
    FINANCE_SIGNED = 'FINANCE_SIGNED', 'Finance signed (closed)'
    TECHNICAL_REHEARSED = 'TECHNICAL_REHEARSED', 'Technically rehearsed (closed)'
    ENABLED = 'ENABLED', 'Enabled (open)'
    SUSPENDED = 'SUSPENDED', 'Suspended (closed)'
    WITHDRAWN = 'WITHDRAWN', 'Withdrawn (closed)'


GATE_ACTIVATION_SEQUENCE = [
    GateStatusChoices.DESIGNED,
    GateStatusChoices.LEGALLY_REVIEWED,
    GateStatusChoices.PARTNER_VERIFIED,
    GateStatusChoices.FINANCE_SIGNED,
    GateStatusChoices.TECHNICAL_REHEARSED,
    GateStatusChoices.ENABLED,
]


class RoleProfileTypeChoices(models.TextChoices):
    ADVERTISING_ONLY = 'ADVERTISING_ONLY', 'Advertising-only'
    SOFTWARE_ONLY = 'SOFTWARE_ONLY', 'Software-only'
    FACILITATED_ORDER = 'FACILITATED_ORDER', 'Facilitated order'
    DISCLOSED_AGENT = 'DISCLOSED_AGENT', 'Disclosed commercial agent'
    REGULATED_INTRODUCER = 'REGULATED_INTRODUCER', 'Regulated introducer (gated)'
    CROSS_BORDER_ORCHESTRATOR = 'CROSS_BORDER_ORCHESTRATOR', 'Cross-border orchestrator (gated)'
    PRINCIPAL_SELLER = 'PRINCIPAL_SELLER', 'Principal seller / owner (out of scope)'


GATED_ROLE_PROFILE_TYPES = {
    RoleProfileTypeChoices.REGULATED_INTRODUCER,
    RoleProfileTypeChoices.CROSS_BORDER_ORCHESTRATOR,
    RoleProfileTypeChoices.PRINCIPAL_SELLER,
}


class SellerOfRecordChoices(models.TextChoices):
    THIRD_PARTY_SELLER = 'THIRD_PARTY_SELLER', 'Named third-party seller/provider'
    PLATFORM = 'PLATFORM', 'DriverXtra contracting entity (SaaS / advertising supply only)'
    NONE = 'NONE', 'No goods/services supply'


class ServicePerformerChoices(models.TextChoices):
    THIRD_PARTY_PROVIDER = 'THIRD_PARTY_PROVIDER', 'Third-party provider'
    PLATFORM = 'PLATFORM', 'DriverXtra (software / advertising service)'
    NONE = 'NONE', 'Not applicable'


class PlatformRoleChoices(models.TextChoices):
    ADVERTISING_PUBLISHER = 'ADVERTISING_PUBLISHER', 'Advertising publisher'
    SOFTWARE_PROVIDER = 'SOFTWARE_PROVIDER', 'Software provider'
    MARKETPLACE_FACILITATOR = 'MARKETPLACE_FACILITATOR', 'Marketplace facilitator'
    DISCLOSED_AGENT = 'DISCLOSED_AGENT', 'Disclosed agent'
    INTRODUCER = 'INTRODUCER', 'Introducer'
    ORCHESTRATOR = 'ORCHESTRATOR', 'Cross-border orchestrator'
    PRINCIPAL = 'PRINCIPAL', 'Principal'


class PaymentRoleChoices(models.TextChoices):
    """Funds-flow reference modes A–F (§10)."""
    NONE = 'NONE', 'No platform-facilitated payment'
    PSP_DIRECT_SETTLEMENT = 'PSP_DIRECT_SETTLEMENT', 'A: PSP partner direct settlement'
    PSP_FACILITATED_SPLIT = 'PSP_FACILITATED_SPLIT', 'B: PSP facilitated split'
    OFF_PLATFORM = 'OFF_PLATFORM', 'C: Off-platform dealer sale'
    SUBSCRIPTION_BILLING = 'SUBSCRIPTION_BILLING', 'D: Subscription billing'
    PSP_CONDITIONAL_PAYOUT = 'PSP_CONDITIONAL_PAYOUT', 'E: PSP-managed conditional payout (gated)'
    PARTNER_REGULATED = 'PARTNER_REGULATED', 'F: Financing/insurance partner (gated)'


GATED_PAYMENT_ROLES = {
    PaymentRoleChoices.PSP_CONDITIONAL_PAYOUT,
    PaymentRoleChoices.PARTNER_REGULATED,
}


class TaxPartyChoices(models.TextChoices):
    SELLER = 'SELLER', 'Seller of record'
    PLATFORM = 'PLATFORM', 'DriverXtra contracting entity'
    BUYER_REVERSE_CHARGE = 'BUYER_REVERSE_CHARGE', 'Buyer (reverse charge)'
    DEEMED_SUPPLIER_PLATFORM = 'DEEMED_SUPPLIER_PLATFORM', 'Platform as deemed supplier'


class InvoiceIssuerChoices(models.TextChoices):
    SELLER = 'SELLER', 'Seller of record'
    PLATFORM = 'PLATFORM', 'DriverXtra contracting entity'
    PSP = 'PSP', 'Payment service provider'
    PARTNER = 'PARTNER', 'Licensed partner'


class QuoteStatusChoices(models.TextChoices):
    ISSUED = 'ISSUED', 'Issued'
    ACCEPTED = 'ACCEPTED', 'Accepted'
    EXPIRED = 'EXPIRED', 'Expired'
    VOID = 'VOID', 'Void'


class QuoteLineTypeChoices(models.TextChoices):
    FACE_VALUE = 'FACE_VALUE', 'Product/service face value'
    DISCOUNT = 'DISCOUNT', 'Discount'
    DELIVERY = 'DELIVERY', 'Delivery'
    TAX = 'TAX', 'Tax'
    PLATFORM_FEE = 'PLATFORM_FEE', 'Platform fee'
