import { useState } from 'react';
import { ArrowDownRight, ArrowRight, Compass, MapPinned, Sparkles } from 'lucide-react';
import './approach-board.css';

const routes = [
  {
    number: '01',
    name: 'The Drowned Bell',
    place: 'Neverwinter · The Chasm',
    note: 'A bell rings beneath a street that has been dry for a century.',
    mood: 'Investigation',
    time: 'A quiet, curious beginning',
    path: 'M72 252 C140 242 144 159 215 172 S294 208 347 145 S430 127 478 66',
    marks: [[72, 252], [215, 172], [347, 145], [478, 66]],
  },
  {
    number: '02',
    name: 'Ash at the Gate',
    place: 'Baldur’s Gate · Outer City',
    note: 'The caravan arrives empty. Its shadows do not.',
    mood: 'Unease',
    time: 'A tense, character-led opening',
    path: 'M72 252 C132 236 132 107 223 120 S296 225 367 193 S415 98 478 66',
    marks: [[72, 252], [223, 120], [367, 193], [478, 66]],
  },
  {
    number: '03',
    name: 'A Crown of Crows',
    place: 'The High Forest · Old trail',
    note: 'A forest messenger offers you a crown—and asks for a name.',
    mood: 'Wonder',
    time: 'A folkloric, open-road beginning',
    path: 'M72 252 C147 240 147 190 204 188 S267 76 336 103 S403 148 478 66',
    marks: [[72, 252], [204, 188], [336, 103], [478, 66]],
  },
];

export function ApproachBoard() {
  const [active, setActive] = useState(0);
  const [ready, setReady] = useState(false);
  const route = routes[active];

  return (
    <main className="ab-shell">
      <header className="ab-topbar">
        <div className="ab-brand"><span className="ab-brand-mark"><Compass size={18} /></span><span>FABLE<span className="ab-brand-dot">/</span>FORGE</span></div>
        <div className="ab-edition"><span className="ab-live-dot" /> SOLO CAMPAIGN STUDIO <span className="ab-edition-line" /> SWORD COAST / 1492 DR</div>
        <button className="ab-saved" type="button" onClick={() => setReady(!ready)}>{ready ? 'RETURN TO ROUTES' : 'YOUR NEXT CHAPTER'} <ArrowDownRight size={14} /></button>
      </header>

      <section className="ab-intro">
        <div className="ab-kicker"><span>FIELD NOTES  /  01</span><span className="ab-kicker-rule" /> A STORY, IN THREE DIRECTIONS</div>
        <div className="ab-title-row">
          <h1>Where will<br /><i>you begin?</i></h1>
          <p className="ab-intro-copy">Not a character sheet. Not a blank page.<br />Choose the first strange thing—and let the world<br className="ab-desktop-only" /> gather around your answer.</p>
        </div>
      </section>

      <section className="ab-workspace" aria-label="Choose a story route">
        <div className="ab-route-list">
          <div className="ab-list-heading"><span>CHOOSE AN OPENING</span><span>3 ROUTES</span></div>
          {routes.map((item, index) => (
            <button
              className={`ab-route ${active === index ? 'is-active' : ''}`}
              key={item.number}
              type="button"
              aria-pressed={active === index}
              onClick={() => { setActive(index); setReady(false); }}
            >
              <span className="ab-route-index">{item.number}</span>
              <span className="ab-route-copy"><strong>{item.name}</strong><small>{item.place}</small></span>
              <span className="ab-route-arrow"><ArrowRight size={15} /></span>
            </button>
          ))}
          <div className="ab-margin-note"><Sparkles size={13} /> The story changes with every choice.</div>
        </div>

        <article className="ab-map-card">
          <div className="ab-map-meta"><span><MapPinned size={13} /> THE REALMS, UNFOLDED</span><span>ROUTE {route.number}</span></div>
          <div className="ab-map">
            <div className="ab-map-grid" />
            <div className="ab-contour ab-contour-one" />
            <div className="ab-contour ab-contour-two" />
            <div className="ab-contour ab-contour-three" />
            <span className="ab-map-word ab-word-north">NORTH</span>
            <span className="ab-map-word ab-word-water">THE TRACKLESS SEA</span>
            <span className="ab-map-word ab-word-forest">OLD FOREST ROAD</span>
            <svg className="ab-route-svg" viewBox="0 0 550 310" preserveAspectRatio="none" aria-label={`${route.name} illustrated route`}>
              <path className="ab-route-under" d={route.path} />
              <path className="ab-route-path" d={route.path} />
              {route.marks.map(([x, y], index) => <g key={`${x}-${y}`} className={index === route.marks.length - 1 ? 'ab-destination' : 'ab-waypoint'}>
                <circle cx={x} cy={y} r={index === route.marks.length - 1 ? 11 : 5} />
                {index === route.marks.length - 1 && <circle cx={x} cy={y} r="3" />}
              </g>)}
            </svg>
            <span className="ab-map-stamp">SWORD<br />COAST</span>
            <span className="ab-map-coord">43° 06′ N<br />03° 51′ W</span>
          </div>
          <div className="ab-map-caption"><span>ILLUSTRATIVE ROUTE · NOT TO SCALE</span><span>01 — 03</span></div>
        </article>
      </section>

      <section className="ab-bottom">
        <div className="ab-story">
          <div className="ab-story-label">THE FIRST THREAD <span>{route.mood.toUpperCase()}</span></div>
          <div className="ab-story-content">
            <h2>{route.name}</h2>
            <p>{route.note}</p>
          </div>
          <div className="ab-story-place"><span className="ab-pin" />{route.place}</div>
        </div>
        <div className="ab-action-zone">
          <div className="ab-duration">{route.time}</div>
          {!ready ? (
            <button className="ab-begin" type="button" onClick={() => setReady(true)}>FOLLOW THIS THREAD <ArrowRight size={16} /></button>
          ) : (
            <div className="ab-ready" role="status">
              <span><Sparkles size={15} /> YOUR STORY IS READY</span>
              <button type="button" onClick={() => setReady(false)}>Choose another route <ArrowRight size={14} /></button>
            </div>
          )}
        </div>
      </section>
      <footer className="ab-footer"><span>MADE FOR ONE PLAYER & ONE IMPOSSIBLE QUESTION</span><span>NO WRONG TURNINGS <b>✳</b></span></footer>
    </main>
  );
}