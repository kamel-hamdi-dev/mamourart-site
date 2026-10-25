// Independent expected copy. Never derive expectations from the page's messages.
const assert = require('node:assert/strict');
const EXPECTED = {
  fr: {
    go: 'GO fictif enregistré pour M-03 uniquement. Aucune fusion ni exécution réelle.',
    'no-go': 'NO-GO fictif enregistré pour M-03. Proposition bloquée ; correction et nouvelle revue requises. Aucune action réelle.',
    reset: 'Aucune décision simulée. Aucune action réelle.'
  },
  en: {
    go: 'Fictional GO recorded for M-03 only. No real merge or execution.',
    'no-go': 'Fictional NO-GO recorded for M-03. Proposal blocked; correction and a new review required. No real action.',
    reset: 'No simulated decision. No real action.'
  }
};
function assertDecision(text, language, decision) {
  assert.equal(text.trim(), EXPECTED[language][decision], `Exact ${decision} decision (${language})`);
}
const NETWORK_ANNOTATIONS = {
  fr: 'TOPOLOGIE CONCEPTUELLE · CONTRÔLE HUMAIN',
  en: 'CONCEPT TOPOLOGY · HUMAN OVERSIGHT'
};
function assertNetworkAnnotation(text, language) {
  assert.equal(text.trim(), NETWORK_ANNOTATIONS[language], `Network annotation (${language})`);
}
module.exports = {EXPECTED, assertDecision, assertNetworkAnnotation};
