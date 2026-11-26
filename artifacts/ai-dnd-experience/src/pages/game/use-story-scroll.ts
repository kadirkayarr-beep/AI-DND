import { useCallback, useEffect, useRef, useState } from 'react';
import type { TranscriptEntry } from '@/components/campaign-transcript';
import { transcriptFollowsBottom } from '@/lib/play-viewport';

/** The story box's own scroll: whether it follows the bottom, and what counts as the reader leaving it. */
export function useStoryScroll({ entries, phase, sessionId, setResultCue, setNewResponseEntryIndex }: {
  entries: TranscriptEntry[];
  phase: string;
  sessionId: string;
  setResultCue: (cue: string) => void;
  setNewResponseEntryIndex: (index: number | null) => void;
}) {
  const storyScrollRef = useRef<HTMLDivElement | null>(null);
  // The story box can be rebuilt without the entry count changing: the effects below follow the node itself (D-089).
  const [storyNode, setStoryNode] = useState<HTMLDivElement | null>(null);
  const attachStory = useCallback((node: HTMLDivElement | null) => {
    storyScrollRef.current = node;
    setStoryNode(node);
  }, []);
  const wasAtBottom = useRef(true);
  const storyLayoutRef = useRef<{ width: number; height: number; contentHeight: number; top: number } | null>(null);
  const storyLayoutScrollTopRef = useRef<number | null>(null);
  // The reader's own wheel, touch, key, pointer or focus move inside the story.
  const readerInputAt = useRef(-Infinity);
  const readerIsScrolling = () => performance.now() - readerInputAt.current < 500;
  const readStoryLayout = (node: HTMLDivElement) => ({
    width: node.clientWidth, height: node.clientHeight, contentHeight: node.scrollHeight, top: node.scrollTop,
  });
  // A layout change moves the view by at most what it resized or grew by. A scroll that leaves the view farther from the
  // bottom than that was not made by the layout (find in page, a screen reader, the reader), whatever the clock says (D-088, D-090).
  const layoutExplainsPosition = (
    previous: { width: number; height: number; contentHeight: number },
    current: { width: number; height: number; contentHeight: number; top: number },
  ) => {
    const changed = previous.width !== current.width || previous.height !== current.height || previous.contentHeight !== current.contentHeight;
    const allowed = Math.abs(current.height - previous.height) + Math.abs(current.contentHeight - previous.contentHeight);
    return changed && current.contentHeight - current.top - current.height <= allowed;
  };
  const seenEntryCount = useRef(0);
  const isStoryNearBottom = (node: HTMLDivElement) => {
    const hasOwnScroll = node.scrollHeight > node.clientHeight + 2
      && ['auto', 'scroll'].includes(getComputedStyle(node).overflowY);
    return hasOwnScroll
      ? node.scrollHeight - node.scrollTop - node.clientHeight < 80
      : node.getBoundingClientRect().bottom <= window.innerHeight + 80;
  };
  const scrollStoryToBottom = (node: HTMLDivElement) => {
    const hasOwnScroll = node.scrollHeight > node.clientHeight + 2
      && ['auto', 'scroll'].includes(getComputedStyle(node).overflowY);
    if (hasOwnScroll) node.scrollTop = node.scrollHeight;
    else node.lastElementChild?.scrollIntoView({ block: 'end', behavior: 'auto' });
  };

  useEffect(() => {
    const node = storyScrollRef.current;
    const grew = entries.length > seenEntryCount.current;
    seenEntryCount.current = entries.length;
    if (!entries.length || !node) return;
    if (transcriptFollowsBottom(wasAtBottom.current)) {
      scrollStoryToBottom(node);
      return;
    }
    if (grew) setResultCue(`Yeni sonuç geldi. ${entries.length}`);
  }, [entries]);
  useEffect(() => {
    const node = storyScrollRef.current;
    const content = node?.querySelector('[data-testid="transcript-local"]');
    if (!node || !content || typeof ResizeObserver === 'undefined') return;
    storyLayoutRef.current = readStoryLayout(node);
    const observer = new ResizeObserver(() => {
      const previous = storyLayoutRef.current;
      const current = readStoryLayout(node);
      // A resize can clamp scrollTop and queue scroll after this callback.
      if (previous && previous.top !== current.top && layoutExplainsPosition(previous, current)) storyLayoutScrollTopRef.current = current.top;
      storyLayoutRef.current = current;
      // The reader's scroll event may still be queued behind this callback: their move is not undone first (D-090).
      if (readerIsScrolling()) return;
      if (transcriptFollowsBottom(wasAtBottom.current)) scrollStoryToBottom(node);
    });
    // The reader can shrink without changing the transcript content box.
    observer.observe(node);
    observer.observe(content);
    const noteReaderInput = () => { readerInputAt.current = performance.now(); };
    const readerInputs = ['wheel', 'touchstart', 'touchmove', 'keydown', 'pointerdown', 'focusin'];
    readerInputs.forEach(type => node.addEventListener(type, noteReaderInput, { passive: true }));
    return () => {
      observer.disconnect();
      readerInputs.forEach(type => node.removeEventListener(type, noteReaderInput));
    };
  }, [storyNode]);
  const handleStoryScroll = (event?: { currentTarget: EventTarget | null }) => {
    const node = storyScrollRef.current;
    if (!node) return;
    // Moving the document does not express reading intent in this own scroller.
    if (event?.currentTarget === window && node.scrollHeight > node.clientHeight + 2
      && ['auto', 'scroll'].includes(getComputedStyle(node).overflowY)) return;
    const previous = storyLayoutRef.current;
    const current = readStoryLayout(node);
    storyLayoutRef.current = current;
    const layoutScrollTop = storyLayoutScrollTopRef.current;
    storyLayoutScrollTopRef.current = null;
    // Layout can dispatch scroll before ResizeObserver. Keep the preference
    // from before that resize; genuine same-layout scrolling still updates it.
    // Only a move the layout change can explain is layout, however soon after the reader's input it lands.
    const readerScroll = readerIsScrolling();
    if (readerScroll) readerInputAt.current = performance.now();
    if ((previous && layoutExplainsPosition(previous, current)) || layoutScrollTop === node.scrollTop) {
      if (transcriptFollowsBottom(wasAtBottom.current)) scrollStoryToBottom(node);
      return;
    }
    wasAtBottom.current = isStoryNearBottom(node);
    if (wasAtBottom.current) {
      setNewResponseEntryIndex(null);
      setResultCue('');
    }
  };
  useEffect(() => {
    window.addEventListener('scroll', handleStoryScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleStoryScroll);
  }, [phase, sessionId]);

  return { storyScrollRef, attachStory, wasAtBottom, handleStoryScroll };
}
