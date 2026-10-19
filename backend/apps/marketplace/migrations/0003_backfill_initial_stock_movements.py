from django.db import migrations


def backfill_initial_stock_movements(apps, schema_editor):
    SparePartListing = apps.get_model('marketplace', 'SparePartListing')
    StockMovement = apps.get_model('marketplace', 'StockMovement')

    for listing in SparePartListing.objects.filter(stock_quantity__gt=0):
        # Idempotent: skip any listing that already has any StockMovement (or specifically an INITIAL movement)
        if StockMovement.objects.filter(listing=listing).exists():
            continue

        StockMovement.objects.create(
            listing=listing,
            delta=listing.stock_quantity,
            resulting_quantity=listing.stock_quantity,
            reason='INITIAL',
            actor=None,
            note='Backfill',
        )


def rollback_backfill_stock_movements(apps, schema_editor):
    StockMovement = apps.get_model('marketplace', 'StockMovement')
    # Delete only the backfill movements created by this migration
    StockMovement.objects.filter(
        reason='INITIAL',
        note='Backfill',
        actor__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    atomic = True

    dependencies = [
        ('marketplace', '0002_add_low_stock_threshold_and_stock_movement'),
    ]

    operations = [
        migrations.RunPython(
            backfill_initial_stock_movements,
            rollback_backfill_stock_movements,
        ),
    ]
