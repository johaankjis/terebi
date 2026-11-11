import assert from 'node:assert/strict';
import { test } from 'node:test';
import { describeResult, drawLandmarks } from '../src/lib/practice.js';
import { loadRecognizer } from '../src/lib/recognizer.js';

const result = (name, score) => ({ landmarks: [[{ x: .2, y: .3, z: .5 }]], gestures: [[{ categoryName: name, score }]] });

test('practice distinguishes no hand, low confidence, and all three moves', () => {
  assert.equal(describeResult({}).status, 'no_hand');
  for (const [name, move] of [['Closed_Fist','rock'],['Open_Palm','paper'],['Victory','scissors']]) {
    const d = describeResult(result(name, .85));
    assert.equal(d.status, 'recognized'); assert.equal(d.move, move); assert.equal(d.score, .85);
    assert.deepEqual(d.landmarks, [{x: .2, y: .3}]);
    assert.equal(describeResult(result(name, .59)).status, 'low_confidence');
  }
  assert.equal(describeResult(result('None', .99)).status, 'low_confidence');
});

test('diagnostics bound and filter landmark coordinates', () => {
  const d = describeResult({landmarks: [Array.from({length: 50}, (_, i) => ({x: i === 1 ? NaN : .5, y: .2}))]});
  assert.equal(d.landmarks.length, 20);
});

test('overlay matches contained video aspect ratio and clears old landmarks', () => {
  const seen=[];
  const ctx={clearRect(...a){seen.push(['clear',...a]);},beginPath(){},moveTo(){},lineTo(){},stroke(){},arc(...a){seen.push(['point',...a]);},fill(){}};
  const canvas={getContext:()=>ctx,clientWidth:400,clientHeight:300};
  drawLandmarks(canvas,{videoWidth:1600,videoHeight:900},[{x:0,y:0}]);
  assert.deepEqual(seen[1].slice(0,3), ['point',0,37.5]);
  drawLandmarks(canvas,{},[]); assert.equal(seen.at(-1)[0], 'clear');
});

test('loader reports which local initialization stage fails', async () => {
  const stages=[];
  await assert.rejects(loadRecognizer({onStage:s=>stages.push(s), importModule:async()=>({FilesetResolver:{forVisionTasks:async()=>{throw new Error('failed');}}})}));
  assert.deepEqual(stages, ['runtime','wasm']);
});
