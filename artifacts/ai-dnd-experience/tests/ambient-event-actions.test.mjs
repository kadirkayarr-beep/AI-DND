import assert from 'node:assert/strict';
import path from 'node:path';
import { after, before, test } from 'node:test';

process.env.PORT ||= '4179';
process.env.BASE_PATH ||= '/';
delete process.env.REPL_ID;

let vite;
let renderPanel;
let isActiveBlueAmbientEvent;
let createAmbientEventActionRequest;
let findPersistedAmbientEventResult;

const blueEvent = {
  event_id: 'city_test_traveler',
  instance_id: 'ambient-instance-blue',
  variation_id: 'v1',
  event_type: 'BLUE',
  repeat_group: 'test-traveler',
  count: 1,
};

const presentedReferent = {
  id: 'referent-blue',
  event_instance_id: blueEvent.instance_id,
  kind: 'ambient_event',
  description: 'A temporary visitor',
  source_turn: 1,
  lifecycle: 'presented',
  promoted_npc_id: null,
};

before(async () => {
  const { createServer } = await import('vite');
  vite = await createServer({
    configFile: path.join(process.cwd(), 'vite.config.ts'),
    server: { middlewareMode: true },
    appType: 'custom',
    logLevel: 'silent',
  });
  const component = await vite.ssrLoadModule('/src/components/ambient-event-actions.tsx');
  const React = await import('react');
  const { renderToStaticMarkup } = await import('react-dom/server');

  renderPanel = (props) => renderToStaticMarkup(
    React.createElement(component.AmbientEventActionPanel, props),
  );
  isActiveBlueAmbientEvent = component.isActiveBlueAmbientEvent;
  createAmbientEventActionRequest = component.createAmbientEventActionRequest;
  findPersistedAmbientEventResult = component.findPersistedAmbientEventResult;
});

after(async () => {
  await vite?.close();
});

const basePanelProps = {
  event: blueEvent,
  referents: [presentedReferent],
  result: null,
  retryRequest: null,
  sending: false,
  hasError: false,
  onAction() {},
  onRetry() {},
};

test('only a presented BLUE ambient event exposes immersive Interact and Observe controls', () => {
  const html = renderPanel(basePanelProps);

  assert.match(html, /data-testid="panel-ambient-event"/);
  assert.match(html, /DİKKATİNİ ÇEKEN/);
  assert.match(html, /A temporary visitor/);
  assert.doesNotMatch(html, /Mavi olay/);
  assert.match(html, /data-testid="button-ambient-action-interact"/);
  assert.match(html, /Etkileşime geç/);
  assert.match(html, /data-testid="button-ambient-action-observe"/);
  assert.match(html, /Gözlemle/);
  assert.equal(isActiveBlueAmbientEvent(blueEvent, [presentedReferent]), true);
});

test('GREEN events and BLUE events without a presented referent remain atmospheric', () => {
  const greenHtml = renderPanel({
    ...basePanelProps,
    event: { ...blueEvent, event_type: 'GREEN' },
  });
  const promotedHtml = renderPanel({
    ...basePanelProps,
    referents: [{ ...presentedReferent, lifecycle: 'promoted' }],
  });

  assert.equal(greenHtml, '');
  assert.equal(promotedHtml, '');
  assert.equal(
    isActiveBlueAmbientEvent({ ...blueEvent, event_type: 'GREEN' }, [presentedReferent]),
    false,
  );
  assert.equal(
    isActiveBlueAmbientEvent(blueEvent, [{ ...presentedReferent, lifecycle: 'promoted' }]),
    false,
  );
});

test('action requests use a single generated UUIDv4 and preserve the selected action', () => {
  const fixedUuid = '00000000-0000-4000-8000-000000000051';
  let generated = 0;
  const request = createAmbientEventActionRequest(
    'session-1',
    blueEvent.instance_id,
    'interact',
    () => {
      generated += 1;
      return fixedUuid;
    },
  );

  assert.equal(generated, 1);
  assert.deepEqual(request, {
    sessionId: 'session-1',
    eventInstanceId: blueEvent.instance_id,
    data: { action_id: fixedUuid, action: 'interact' },
  });
  assert.match(
    request.data.action_id,
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
});

test('all four server statuses render as player-facing outcomes without raw internal codes', () => {
  const labels = {
    APPLIED: 'Karşılaşma ilerledi.',
    REJECTED: 'Şu anda buna müdahale edemiyorsun.',
    NO_EFFECT: 'Bir süre gözlemliyorsun; belirgin bir değişiklik olmuyor.',
    ALREADY_APPLIED: 'Bu karşılaşma zaten gelişti.',
  };

  for (const [status, label] of Object.entries(labels)) {
    const html = renderPanel({
      ...basePanelProps,
      result: {
        event_instance_id: blueEvent.instance_id,
        action_id: '00000000-0000-4000-8000-000000000051',
        status,
        reason_code: 'server_reason',
        transition_id: null,
        canonical_event_id: null,
      },
    });

    assert.match(html, new RegExp(`data-status="${status}"`));
    assert.match(html, new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
    assert.doesNotMatch(html, new RegExp(`>${status}<`));
    assert.doesNotMatch(html, /server_reason/);
    assert.doesNotMatch(html, /ambient-event-status-code|ambient-event-reason-code/);
  }
});

test('a failed request exposes retry while keeping its original request ID', () => {
  const fixedUuid = '00000000-0000-4000-8000-000000000052';
  const request = createAmbientEventActionRequest(
    'session-1',
    blueEvent.instance_id,
    'observe',
    () => fixedUuid,
  );
  const html = renderPanel({
    ...basePanelProps,
    retryRequest: request,
    hasError: true,
  });

  assert.match(html, /data-testid="button-ambient-action-retry"/);
  assert.match(html, /data-testid="ambient-action-network-error"/);
  assert.doesNotMatch(html, /data-testid="button-ambient-action-interact"/);
  assert.doesNotMatch(html, /data-testid="button-ambient-action-observe"/);
  assert.equal(request.data.action_id, fixedUuid);
  assert.equal(request.data.action, 'observe');
});

test('persisted applied outcomes are reconstructed only from the server journal', () => {
  const state = {
    journal: {
      notable_events: [{
        event_id: 'canonical-event-1',
        event_type: 'ambient_event_outcome',
        event_result: {
          event_instance_id: blueEvent.instance_id,
          action_id: '00000000-0000-4000-8000-000000000051',
          action: 'interact',
          status: 'APPLIED',
          reason_code: 'referent_promoted',
          transition_id: 'npc-traveler-1',
        },
      }],
    },
  };

  assert.deepEqual(
    findPersistedAmbientEventResult(state, blueEvent.instance_id),
    {
      event_instance_id: blueEvent.instance_id,
      action_id: '00000000-0000-4000-8000-000000000051',
      status: 'APPLIED',
      reason_code: 'referent_promoted',
      transition_id: 'npc-traveler-1',
      canonical_event_id: 'canonical-event-1',
    },
  );
  assert.equal(findPersistedAmbientEventResult(state, 'another-event'), null);
});