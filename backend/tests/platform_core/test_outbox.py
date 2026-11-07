import pytest
from django.core.management import call_command
from django.db import transaction

from platform_core.events import outbox
from platform_core.events.models import ConsumedEvent, OutboxEvent, OutboxStatusChoices
from platform_core.events.outbox import emit_event, publish_pending_events, register_consumer


@pytest.fixture
def clean_consumers():
    saved = {topic: list(entries) for topic, entries in outbox._consumers.items()}
    outbox._consumers.clear()
    yield
    outbox._consumers.clear()
    outbox._consumers.update(saved)


def _emit(key='test.event:1', topic='test.event'):
    return emit_event(topic, aggregate_type='Thing', aggregate_id='1', payload={'a': 1}, idempotency_key=key)


@pytest.mark.django_db
def test_emit_event_is_idempotent_by_key():
    first = _emit()
    second = _emit()
    assert first.id == second.id
    assert OutboxEvent.objects.count() == 1
    assert first.status == OutboxStatusChoices.PENDING


@pytest.mark.django_db
def test_event_rolls_back_with_business_transaction():
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            _emit()
            raise RuntimeError('business failure')
    assert OutboxEvent.objects.count() == 0


@pytest.mark.django_db
def test_publish_delivers_once_per_consumer_even_when_rerun(clean_consumers):
    received = []

    @register_consumer('test.event', 'collector')
    def collector(event):
        received.append(event.id)

    event = _emit()
    assert publish_pending_events() == {'published': 1, 'failed': 0}

    # Simulate a redelivery: reset to PENDING and publish again.
    OutboxEvent.objects.filter(pk=event.pk).update(status=OutboxStatusChoices.PENDING)
    publish_pending_events()

    assert received == [event.id]
    assert ConsumedEvent.objects.filter(consumer='collector', event_id=event.id).count() == 1
    event.refresh_from_db()
    assert event.status == OutboxStatusChoices.PUBLISHED
    assert event.published_at is not None


@pytest.mark.django_db
def test_failing_consumer_marks_failed_and_retry_skips_successful_consumers(clean_consumers):
    calls = {'ok': 0, 'flaky': 0}
    state = {'fail': True}

    @register_consumer('test.event', 'ok')
    def ok(event):
        calls['ok'] += 1

    @register_consumer('test.event', 'flaky')
    def flaky(event):
        calls['flaky'] += 1
        if state['fail']:
            raise ValueError('downstream unavailable')

    event = _emit()
    assert publish_pending_events() == {'published': 0, 'failed': 1}
    event.refresh_from_db()
    assert event.status == OutboxStatusChoices.FAILED
    assert event.attempts == 1
    assert 'ValueError' in event.last_error
    assert not ConsumedEvent.objects.filter(consumer='flaky').exists()

    state['fail'] = False
    assert publish_pending_events() == {'published': 1, 'failed': 0}
    assert calls == {'ok': 1, 'flaky': 2}


@pytest.mark.django_db
def test_publish_command_reports_counts(clean_consumers):
    _emit()
    from io import StringIO
    out = StringIO()
    call_command('publish_outbox_events', stdout=out)
    assert '1 published' in out.getvalue()
