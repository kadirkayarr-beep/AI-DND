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
let ambientFollowUpMove;

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
  ambientFollowUpMove = component.ambientFollowUpMove;
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

test('a click on an event continues as a real move in the story, never as a bare status line', () => {
  const move = (action, status) => ambientFollowUpMove(action, status);
  // D-128: a joined event is already its own story turn on the server (history row and undo checkpoint).
  // A second, automatic turn would make one click two records and Undo would take back only the second.
  assert.equal(move('interact', 'APPLIED'), null);
  // Observing changes nothing on the server, so the story move is the click's only record.
  assert.equal(move('observe', 'NO_EFFECT'), 'Bir süre durup çevremi gözlemliyorum.');
  assert.equal(move('interact', 'REJECTED'), null);
  assert.equal(move('interact', 'ALREADY_APPLIED'), null);
});

test('all four server statuses render as player-facing outcomes without raw internal codes', () => {
  const labels = {
    APPLIED: 'Yanlarına gidiyorsun.',
    REJECTED: 'Şu anda buna müdahale edemiyorsun.',
    NO_EFFECT: 'Bir süre duruyorsun.',
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
test('the buttons follow the engine: actionable.can_interact decides, and presented is only the fallback for an older server', () => {
  const withActionable = (actionable) => renderPanel({
    ...basePanelProps,
    event: { ...blueEvent, actionable },
  });
  const hasButtons = (html) => /data-testid="button-ambient-action-interact"/.test(html);

  assert.equal(hasButtons(withActionable({ can_interact: false, reason: 'in_combat' })), false);
  assert.equal(hasButtons(withActionable({ can_interact: true, reason: null })), true);
  assert.equal(hasButtons(renderPanel(basePanelProps)), true);
  // Not presented but the engine says yes: the engine wins.
  assert.equal(isActiveBlueAmbientEvent(
    { ...blueEvent, actionable: { can_interact: true, reason: null } },
    [{ ...presentedReferent, lifecycle: 'promoted' }],
  ), true);
});

test('a refusal shows the engine message when there is one', () => {
  const html = renderPanel({
    ...basePanelProps,
    result: {
      event_instance_id: blueEvent.instance_id,
      action_id: '00000000-0000-4000-8000-000000000053',
      status: 'REJECTED',
      reason_code: 'event_expired',
      transition_id: null,
      canonical_event_id: null,
      message: 'Onlar çoktan dağıldı.',
    },
  });

  assert.match(html, /Onlar çoktan dağıldı\./);
  assert.doesNotMatch(html, /Şu anda buna müdahale edemiyorsun/);
  assert.doesNotMatch(html, /event_expired/);
});

// D-128 review: the joined click is the server's live undo target and its own history row, so the screen must name it.
async function runAmbientClick(status, { campaignRead = 'fresh' } = {}) {
  const { readFile } = await import('node:fs/promises');
  const vm = await import('node:vm');
  const ts = (await import('typescript')).default;
  const { historyToEntries } = await vite.ssrLoadModule('/src/lib/transcript-history.ts');
  const source = await readFile(new URL('../src/pages/game-browser.tsx', import.meta.url), 'utf8');
  const ast = ts.createSourceFile('game-browser.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const component = ast.statements.find((n) => ts.isFunctionDeclaration(n) && n.name?.text === 'GameBrowser');
  const code = component.body.statements.find((n) => ts.isVariableStatement(n)
    && n.declarationList.declarations.some((d) => d.name.getText(ast) === 'submitAmbientEventAction'));
  assert.ok(code);
  const executable = ts.transpileModule(`${code.getText(ast)}\nglobalThis.click = submitAmbientEventAction;`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
  const calls = { lastTurn: [], undoneJustNow: [], entries: [], turns: [], campaignReads: [] };
  let mutation;
  const request = createAmbientEventActionRequest('session-a', blueEvent.instance_id, 'interact',
    () => '00000000-0000-4000-8000-000000000128');
  const history = [
    { player_message: 'Önceki hamle', narration: 'Önceki anlatım.' },
    { player_message: 'Yolcuyla konuşmaya gidiyorum.', narration: 'Yanlarına gidiyorsun; karşında yorgun bir yolcu var.' },
  ];
  const env = {
    sessionId: 'session-a', campaignId: 'campaign-a',
    activeSessionRef: { current: 'session-a' },
    pendingAmbientActionRef: { current: null },
    blockingMutation: () => null, setNotice() {},
    setAmbientActionRequest() {}, setAmbientActionError() {}, setAmbientActionResult() {},
    nextRevision: () => 1,
    queryClient: {},
    applyGameState: (_client, _session, state) => campaignRead === 'fresh' || state !== 'campaign-state',
    ambientFollowUpMove,
    submitTurnRef: { current: (...args) => calls.turns.push(args) },
    setLastTurn: (value) => calls.lastTurn.push(value),
    setUndoneJustNow: (value) => calls.undoneJustNow.push(value),
    setEntries: (value) => calls.entries.push(value),
    historyToEntries,
    getCampaign: async (id) => { calls.campaignReads.push(id); return { state: 'campaign-state', history }; },
    resolveAmbientEventAction: { mutate: (_vars, callbacks) => { mutation = callbacks; } },
  };
  vm.runInNewContext(executable, Object.assign(env, { globalThis: env }));
  env.click(request);
  mutation.onSuccess({ state: 'reply-state', result: { action_id: request.data.action_id, status } });
  await new Promise((resolve) => setTimeout(resolve, 0));
  return { calls, request };
}

test('a joined event is the turn the Undo bar names, and its story line shows at once', async () => {
  const { calls, request } = await runAmbientClick('APPLIED');
  assert.deepEqual(calls.turns, []);
  assert.equal(calls.lastTurn.length, 1);
  assert.equal(calls.lastTurn[0].sessionId, 'session-a');
  assert.equal(calls.lastTurn[0].actionId, request.data.action_id);
  assert.deepEqual(calls.undoneJustNow, [false]);
  assert.deepEqual(calls.campaignReads, ['campaign-a']);
  assert.equal(calls.entries.length, 1);
  assert.ok(calls.entries[0].some((entry) => entry.text === 'Yanlarına gidiyorsun; karşında yorgun bir yolcu var.'));
});

test('a click that changed nothing leaves the last turn and the story as they were', async () => {
  for (const status of ['REJECTED', 'ALREADY_APPLIED', 'NO_EFFECT']) {
    const { calls } = await runAmbientClick(status);
    assert.deepEqual(calls.lastTurn, [], status);
    assert.deepEqual(calls.entries, [], status);
  }
});

test('an older campaign read after a joined event never overwrites a newer story', async () => {
  const { calls } = await runAmbientClick('APPLIED', { campaignRead: 'stale' });
  assert.equal(calls.lastTurn.length, 1);
  assert.deepEqual(calls.entries, []);
});
