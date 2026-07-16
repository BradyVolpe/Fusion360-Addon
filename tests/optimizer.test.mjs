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
assert.doesNotThrow(() => new vm.Script(scriptMatch[1]), 'the complete browser script must parse');

const pureScript = scriptMatch[1].split('// ===== UI =====')[0];
const context = {};
vm.createContext(context);
vm.runInContext(
  `${pureScript}\nthis.optimizerApi = { parseCSV, parseQuantity, parsePercentage, expandPartsForQuantity, buildHardwoodBlanks, calculateHardwoodOrder, solveHardwood, planHardwoodMaterials, collapseWarnings, aggregateWarnings, isBetterResult, solve, solveStrict2Stage, solveRelaxed2Stage, generateCutSequence };`,
  context,
);

const api = context.optimizerApi;
const fixture = fs.readFileSync(path.join(testDir, 'fixtures', 'CabinetParams.csv'), 'utf8');
const parsed = api.parseCSV(fixture);
const hardwoodFixture = fs.readFileSync(path.join(testDir, 'fixtures', 'FaceFrameHardwood.csv'), 'utf8');
const hardwoodParsed = api.parseCSV(hardwoodFixture);
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

test('order allowance accepts only percentages from 0 through 100', () => {
  assert.equal(api.parsePercentage('0'), 0);
  assert.equal(api.parsePercentage('20'), 20);
  assert.equal(api.parsePercentage('100'), 100);
  for (const value of ['-1', '100.1', '150', '', 'not-a-number']) {
    assert.equal(api.parsePercentage(value), null, `expected ${JSON.stringify(value)} to be rejected`);
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

test('hardwood fixture models 1-1/2 inch parts as two 4/4 glue-up laminations', () => {
  assert.equal(hardwoodParsed.parts.length, 8);
  assert.equal(hardwoodParsed.warnings.length, 0);

  const build = api.buildHardwoodBlanks(hardwoodParsed.parts, 1, 0.75, 0.25, 1);
  assert.equal(build.warnings.length, 0);
  assert.equal(build.blanks.length, 12);
  assert.equal(build.blanks.filter(blank => blank.finishedThickness === 1.5).length, 8);
  assert.ok(build.blanks.filter(blank => blank.finishedThickness === 1.5).every(blank => blank.layerCount === 2));
  assert.ok(build.blanks.filter(blank => blank.finishedThickness === 0.75).every(blank => blank.layerCount === 1));
  assert.equal(build.laminationGroups.find(group => group.finishedThickness === 1.5).thicknessMargin, 0);
});

test('hardwood quantity doubles finished parts, laminations, and order requirement', () => {
  const one = api.buildHardwoodBlanks(hardwoodParsed.parts, 1, 0.75, 0.25, 1);
  const two = api.buildHardwoodBlanks(hardwoodParsed.parts, 2, 0.75, 0.25, 1);
  const oneOrder = api.calculateHardwoodOrder(one.blanks, 1, 6, 20);
  const twoOrder = api.calculateHardwoodOrder(two.blanks, 1, 6, 20);

  assert.equal(two.blanks.length, one.blanks.length * 2);
  assert.equal(twoOrder.netBoardFeet, oneOrder.netBoardFeet * 2);
  assert.equal(twoOrder.netLinearFeet, oneOrder.netLinearFeet * 2);
});

test('hardwood order reports board feet and width-dependent linear feet with allowance', () => {
  const build = api.buildHardwoodBlanks(hardwoodParsed.parts, 1, 0.75, 0.25, 1);
  const order = api.calculateHardwoodOrder(build.blanks, 1, 6, 20);

  assert.equal(order.netBoardFeet.toFixed(3), '7.378');
  assert.equal(order.netLinearFeet.toFixed(3), '14.757');
  assert.equal(order.orderBoardFeet, 9);
  assert.equal(order.orderLinearFeet, 18);
});

test('hardwood order never recommends less stock than its selected cut map consumes', () => {
  const build = api.buildHardwoodBlanks(hardwoodParsed.parts, 1, 0.75, 0.25, 1);
  const layout = api.solveHardwood(build.blanks, 6, 120, 0.125, 1);
  const layoutBoardFeet = layout.boards.length * 6 * 120 * 1 / 144;
  const order = api.calculateHardwoodOrder(build.blanks, 1, 6, 20, layoutBoardFeet);

  assert.equal(layout.boards.length, 2);
  assert.equal(layoutBoardFeet, 10);
  assert.equal(order.orderBoardFeet, 10);
  assert.equal(order.orderLinearFeet, 20);
});

test('hardwood solver keeps Height along board length and places every glue-up layer', () => {
  const build = api.buildHardwoodBlanks(hardwoodParsed.parts, 1, 0.75, 0.25, 1);
  const result = api.solveHardwood(build.blanks, 6, 120, 0.125, 1);
  const placed = result.boards.flatMap(board => board.placements);

  assert.equal(result.warnings.length, 0);
  assert.equal(result.placedCount, 12);
  assert.equal(placed.length, 12);
  assert.ok(placed.every(placement => placement.rotated));
  assert.ok(placed.every(placement => placement.placedW === placement.part.height));
  assert.ok(placed.every(placement => placement.placedH === placement.part.width));
});

test('hardwood solver rejects a blank that only fits by rotating across grain', () => {
  const blank = {
    partId: 'cross-grain trap', cabId: 'Test', width: 5, height: 50,
    finishedThickness: 0.75, stockThickness: 0.75, layerNumber: 1, layerCount: 1,
  };
  const result = api.solveHardwood([blank], 60, 6, 0, 0);

  assert.equal(result.placedCount, 0);
  assert.equal(result.boards.length, 0);
  assert.match(result.warnings[0], /does not fit grain-correct/);
});

test('hardwood plans keep different species in separate orders and boards', () => {
  const parts = [
    { partId: 'maple rail', cabId: 'A', width: 2, height: 30, thickness: 0.75, material: 'Maple', materialProvided: true },
    { partId: 'cherry rail', cabId: 'B', width: 2, height: 30, thickness: 0.75, material: 'Cherry', materialProvided: true },
  ];
  const build = api.buildHardwoodBlanks(parts, 1, 0.75, 0, 0);
  const plans = api.planHardwoodMaterials(build.blanks, 1, 6, 20, 6, 96, 0.125, 1);

  assert.deepEqual(Array.from(plans, plan => plan.material), ['Cherry', 'Maple']);
  assert.equal(plans.length, 2);
  assert.ok(plans.every(plan => plan.layout.boards.length === 1));
  assert.ok(plans.every(plan => plan.layout.boards.every(board => board.placements.every(placement => placement.part.hardwoodMaterial === plan.material))));
});

test('hardwood warning aggregation collapses repeated quantity failures', () => {
  const warnings = api.collapseWarnings(['too wide', 'too wide', 'too long']);
  assert.deepEqual(Array.from(warnings), ['too wide (2 occurrences)', 'too long']);
});
