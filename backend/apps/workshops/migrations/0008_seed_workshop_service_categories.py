from django.db import migrations


def seed_categories(apps, schema_editor):
    WorkshopServiceCategory = apps.get_model('workshops', 'WorkshopServiceCategory')

    categories = [
        ('Routine Servicing & Maintenance', 'routine-servicing-maintenance', 'Standard minor/major servicing, oil and filter replacements', 'wrench', 1),
        ('Brakes & Suspension', 'brakes-suspension', 'Brake pads, discs, suspension arms, shocks and bushes', 'shield-check', 2),
        ('Diagnostics & Electrical', 'diagnostics-electrical', 'OBD-II scans, warning light diagnostics, battery & alternator testing', 'cpu', 3),
        ('Tyres, Wheels & Tracking', 'tyres-wheels-tracking', 'Tyre fitting, balancing, 4-wheel laser alignment', 'disc', 4),
        ('MOT & Safety Inspections', 'mot-safety-inspections', 'Statutory MOT testing and multi-point vehicle health checks', 'file-check', 5),
        ('Engine & Transmission', 'engine-transmission', 'Timing belts, water pumps, clutch replacements and gearbox services', 'cog', 6),
    ]

    for name, slug, desc, icon, order in categories:
        WorkshopServiceCategory.objects.get_or_create(
            name=name,
            defaults={
                'slug': slug,
                'description': desc,
                'icon_name': icon,
                'display_order': order,
            }
        )


def unseed_categories(apps, schema_editor):
    WorkshopServiceCategory = apps.get_model('workshops', 'WorkshopServiceCategory')
    WorkshopServiceCategory.objects.filter(
        slug__in=[
            'routine-servicing-maintenance',
            'brakes-suspension',
            'diagnostics-electrical',
            'tyres-wheels-tracking',
            'mot-safety-inspections',
            'engine-transmission',
        ]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('workshops', '0007_changeorder_tax_breakdown_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_categories, unseed_categories),
    ]

