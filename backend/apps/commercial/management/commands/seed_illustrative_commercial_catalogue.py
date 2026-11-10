"""Load the Master Architecture §6 SKU taxonomy as non-binding catalogue entries.

- Creates SKUs only (no rate schedules, no gates, no approvals).
- SKUs with an illustrative band become ILLUSTRATIVE; gated or undecided SKUs stay DRAFT.
- Price bands are stored as text notes for planning and are never used in calculations.
- Idempotent: existing SKU codes are left untouched.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.commercial.choices import CatalogueStatusChoices
from apps.commercial.models import CommercialSku
from apps.identity.models import User

ILLUSTRATIVE = CatalogueStatusChoices.ILLUSTRATIVE
DRAFT = CatalogueStatusChoices.DRAFT

# (sku_code, name, family, revenue_code, vertical, fee_basis, entitlement, interval, band_note, status)
SKUS = [
    ('DX-LST-PRIVATE', 'Private vehicle listing', 'ADVERTISING', 'ADV-01', 'VEHICLES', 'FLAT_PER_UNIT', 'LISTING',
     'ONE_TIME', 'ILLUSTRATIVE $15–$49 per vehicle / 30-day listing (USD reference only)', ILLUSTRATIVE),
    ('DX-SPONSORED', 'Sponsored placement', 'ADVERTISING', 'ADV-02', 'ADVERTISING', 'FLAT_PER_UNIT', 'CAMPAIGN',
     'ONE_TIME', 'ILLUSTRATIVE $10–$150 per campaign duration/impressions; labelled sponsorship', ILLUSTRATIVE),
    ('DX-DEAL-LAUNCH', 'Dealer Launch', 'SUBSCRIPTION', 'SUB-01', 'VEHICLES', 'RECURRING_FLAT', 'INVENTORY_SLOT',
     'MONTHLY', 'ILLUSTRATIVE $49–$149 / month; fixed active stock cap', ILLUSTRATIVE),
    ('DX-DEAL-GROWTH', 'Dealer Growth', 'SUBSCRIPTION', 'SUB-01', 'VEHICLES', 'RECURRING_FLAT', 'INVENTORY_SLOT',
     'MONTHLY', 'ILLUSTRATIVE $149–$499 / month; usage beyond cap priced separately', ILLUSTRATIVE),
    ('DX-DEAL-ENT', 'Dealer Enterprise', 'SUBSCRIPTION', 'SUB-01', 'VEHICLES', 'CUSTOM_CONTRACT', 'SITE',
     'MONTHLY', 'ILLUSTRATIVE custom, $1,000+ / month; no universal minimum implied', ILLUSTRATIVE),
    ('DX-LEAD-DEALER', 'Qualified dealer lead', 'ADVERTISING', 'ADV-04', 'VEHICLES', 'PER_ACCEPTED_LEAD', 'NONE',
     'PER_EVENT', 'ILLUSTRATIVE $5–$35 per accepted qualified lead', ILLUSTRATIVE),
    ('DX-PARTS-TAKE', 'Parts platform fee', 'COMMERCE', 'COM-01', 'PARTS', 'PERCENT_OF_BASE', 'NONE',
     'PER_EVENT', 'ILLUSTRATIVE 5%–12% of commissionable net order value', ILLUSTRATIVE),
    ('DX-WORKSHOP-SUB', 'Workshop Pro', 'SUBSCRIPTION', 'SUB-02', 'SERVICES', 'RECURRING_FLAT', 'SEAT',
     'MONTHLY', 'ILLUSTRATIVE $39–$199 / month', ILLUSTRATIVE),
    ('DX-SERVICE-BOOK', 'Service booking fee', 'COMMERCE', 'COM-02', 'SERVICES', 'PERCENT_OF_BASE', 'NONE',
     'PER_EVENT', 'UNDECIDED basis: 5%–12% OR $5–$25 (one published basis per SKU required)', DRAFT),
    ('DX-SUPPLIER-PRO', 'Supplier Pro', 'SUBSCRIPTION', 'SUB-03', 'PARTS', 'RECURRING_FLAT', 'NONE',
     'MONTHLY', 'ILLUSTRATIVE $79–$299 / month', ILLUSTRATIVE),
    ('DX-FLEET-ASSET', 'FleetOps per active asset', 'SUBSCRIPTION', 'SUB-04', 'FLEET', 'PER_ACTIVE_ASSET', 'ASSET',
     'MONTHLY', 'ILLUSTRATIVE $5–$20 per active asset / month', ILLUSTRATIVE),
    ('DX-API-BASE', 'Infrastructure API base tier', 'API', 'API-01', 'ENTERPRISE_API', 'RECURRING_FLAT', 'API_QUOTA',
     'MONTHLY', 'ILLUSTRATIVE $500–$2,500 / month plus contracted usage', ILLUSTRATIVE),
    ('DX-REF-EV', 'EV services referral', 'REFERRAL', 'REF-01', 'EV', 'PER_ACCEPTED_LEAD', 'NONE',
     'PER_EVENT', 'ILLUSTRATIVE $5–$40 per accepted, non-duplicate EV lead', ILLUSTRATIVE),
    ('DX-REG-REF', 'Regulated finance/insurance referral', 'REGULATED', 'REG-01', 'FINANCE_INSURANCE',
     'CUSTOM_CONTRACT', 'NONE', 'PER_EVENT', 'GATED — no rate proposed (D06 hold)', DRAFT),
    ('DX-PAYMENT-FEE', 'Payment service-related fee', 'PAYMENT', 'FIN-01', 'PARTS', 'CUSTOM_CONTRACT', 'NONE',
     'PER_EVENT', 'GATED — no rate proposed; PSP economics passed through only as contracted', DRAFT),
]


class Command(BaseCommand):
    help = "Seed the §6 SKU taxonomy as ILLUSTRATIVE/DRAFT catalogue entries with no rates (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument('--created-by', default='', help='Email of the staff user recorded as SKU author.')

    def handle(self, *args, **options):
        author = None
        if options['created_by']:
            author = User.objects.filter(email=options['created_by'].strip().lower()).first()
            if author is None:
                raise CommandError(f"No user with email {options['created_by']}.")

        created = skipped = 0
        with transaction.atomic():
            for code, name, family, revenue, vertical, basis, entitlement, interval, note, status in SKUS:
                if CommercialSku.objects.filter(sku_code=code).exists():
                    skipped += 1
                    continue
                CommercialSku.objects.create(
                    sku_code=code, version=1, name=name, family=family, revenue_code=revenue, vertical=vertical,
                    fee_basis=basis, entitlement_type=entitlement, billing_interval=interval,
                    illustrative_band_note=note, status=status, created_by=author,
                    status_reason='Seeded from Master Architecture v1.0 §6 (non-binding).',
                )
                created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Illustrative catalogue: {created} created, {skipped} already present. No rates, gates or approvals were created."
        ))
