// AST-selected page bodies need the same real feature helper and ephemeral controller as the page.
// No projection is manufactured: old synthetic states remain ordinary, feature-free requests.
import { createPrimalKnowledgeIntent, primalKnowledgeAvailable } from '../../src/lib/primal-knowledge.ts';
import { tacticalMindAvailable } from '../../src/lib/fighter-projection.ts';
export function primalKnowledgeInjection() {
  return { primalKnowledgeAvailable, primalKnowledgeIntent: createPrimalKnowledgeIntent(), redrawPrimalKnowledge() {},
    tacticalMindAvailable, tacticalMindIntent: createPrimalKnowledgeIntent() };
}
