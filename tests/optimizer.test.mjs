import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const testDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(testDir, '..');
const html = fs.readFileSync(path.join(repoRoot, 'index.html'), 'utf8');
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);

assert.ok(scriptMatch, 'index.html must contain an inline script');

const pureScript = scriptMatch[1].split('// ===== UI =====')[0];
const context = {};
vm.createContext(context);
vm.runInContext(
  `${pureScript}\nthis.optimizerApi = { parseCSV, parseQuantity, expandPartsForQuantity, aggregateWarnings, isBetterResult, solve, solveStrict2Stage, solveRelaxed2Stage, generateCutSequence };`,
  context,
);

const api = context.optimizerApi;
const fixture = fs.readFileSync(path.join(testDir, 'fixtures', 'CabinetParams.csv'), 'utf8');
const parsed = api.parseCSV(fixture);
const effectiveSheet = { width: 95.5, height: 47.5, kerf: 0.125 };

function solveFixture(quantity, respectGrain = true) {
  const parts = api.expandPartsForQuantity(parsed.parts, quantity);
  return api.solve(
    parts,
    effectiveSheet.width,
    effectiveSheet.height,
    effectiveSheet.kerf,
    true,
    respectGrain,
  );
}

function placements(result) {
  return result.results.flatMap(material => material.sheets.flatMap(sheet => sheet.placements));
}

test('real cabinet CSV parses all 71 parts without warnings', () => {
  assert.equal(parsed.parts.length, 71);
  assert.equal(parsed.warnings.length, 0);
});

test('quantity accepts only whole cabinet-set counts from 1 through 20', () => {
  assert.equal(api.parseQuantity('1'), 1);
  assert.equal(api.parseQuantity('2'), 2);
  assert.equal(api.parseQuantity('20'), 20);
  for (const value of ['0', '-1', '1.5', '21', '', 'not-a-number']) {
    assert.equal(api.parseQuantity(value), null, `expected ${JSON.stringify(value)} to be rejected`);
  }
});

test('quantity 2 expands and jointly optimizes the real 71-part cabinet set', () => {
  const expanded = api.expandPartsForQuantity(parsed.parts, 2);
  assert.equal(expanded.length, 142);
  assert.equal(expanded.filter(part => part.copyNumber === 1).length, 71);
  assert.equal(expanded.filter(part => part.copyNumber === 2).length, 71);

  const results = [
    solveFixture(2),
    api.solveStrict2Stage(expanded, effectiveSheet.width, effectiveSheet.height, effectiveSheet.kerf),
    api.solveRelaxed2Stage(expanded, effectiveSheet.width, effectiveSheet.height, effectiveSheet.kerf),
  ];

  assert.deepEqual(results.map(result => result.grandParts), [142, 142, 142]);
  assert.deepEqual(results.map(result => result.grandSheets), [9, 10, 10]);
  assert.deepEqual(results.map(result => placements(result).length), [142, 142, 142]);
});

test('maximum quantity 20 remains complete in all three solvers', () => {
  const expanded = api.expandPartsForQuantity(parsed.parts, 20);
  const results = [
    solveFixture(20),
    api.solveStrict2Stage(expanded, effectiveSheet.width, effectiveSheet.height, effectiveSheet.kerf),
    api.solveRelaxed2Stage(expanded, effectiveSheet.width, effectiveSheet.height, effectiveSheet.kerf),
  ];

  assert.equal(expanded.length, 1420);
  assert.deepEqual(results.map(result => result.grandParts), [1420, 1420, 1420]);
  assert.deepEqual(results.map(result => placements(result).length), [1420, 1420, 1420]);
});

test('grain lock keeps every real-cabinet part Height along the sheet long axis', () => {
  for (const quantity of [1, 2]) {
    const optimized = solveFixture(quantity);
    const placed = placements(optimized);

    assert.equal(placed.length, 71 * quantity);
    assert.equal(optimized.warnings.length, 0);
    assert.ok(placed.every(item => item.rotated), 'landscape sheets must rotate Height onto the horizontal long axis');
    assert.ok(placed.every(item => item.placedW === item.part.height));
    assert.ok(placed.every(item => item.placedH === item.part.width));
  }
});

test('grain lock rejects a part that only fits cross-grain', () => {
  const part = {
    partId: 'Cross-grain only',
    cabId: 'Test',
    width: 60,
    height: 40,
    thickness: 0.75,
    material: 'Plywood',
  };

  const locked = api.solve([part], 70, 50, 0, true, true);
  const unlocked = api.solve([part], 70, 50, 0, true, false);

  assert.equal(locked.grandParts, 0);
  assert.match(locked.warnings[0], /doesn't fit grain-correct/);
  assert.equal(unlocked.grandParts, 1);
});

test('all solvers align Height with the long axis of a portrait sheet', () => {
  const part = {
    partId: 'Portrait grain',
    cabId: 'Test',
    width: 20,
    height: 60,
    thickness: 0.75,
    material: 'Plywood',
  };
  const results = [
    api.solve([part], 50, 70, 0, true, true),
    api.solveStrict2Stage([part], 50, 70, 0),
    api.solveRelaxed2Stage([part], 50, 70, 0),
  ];

  for (const result of results) {
    const placed = placements(result);
    assert.equal(result.grandParts, 1);
    assert.equal(placed.length, 1);
    assert.equal(placed[0].rotated, false);
    assert.equal(placed[0].placedW, 20);
    assert.equal(placed[0].placedH, 60);
  }

  const steps = api.generateCutSequence(results[1].results[0].sheets[0], 50, 70, 0, 'strict', 0);
  assert.match(steps.find(step => step.kind === 'rip').label, /from left/);
  assert.match(steps.find(step => step.kind === 'crosscut').label, /from top/);
});

test('incomplete layouts cannot outrank complete layouts with more sheets', () => {
  const complete = { grandParts: 1, grandSheets: 1, grandWaste: '50.0' };
  const incomplete = { grandParts: 0, grandSheets: 0, grandWaste: '0.0' };
  assert.equal(api.isBetterResult(incomplete, complete), false);
  assert.equal(api.isBetterResult(complete, incomplete), true);
});

test('warnings from every solver are surfaced and repeated quantity warnings are aggregated', () => {
  const warnings = api.aggregateWarnings(['bad row'], {
    optimized: { warnings: ['oversized', 'oversized'] },
    strict: { warnings: ['grain mismatch'] },
    relaxed: { warnings: [] },
  });

  assert.equal(warnings.length, 3);
  assert.ok(warnings.includes('CSV: bad row'));
  assert.ok(warnings.includes('Optimized: oversized (2 occurrences)'));
  assert.ok(warnings.includes('Strict Table Saw: grain mismatch'));
});
